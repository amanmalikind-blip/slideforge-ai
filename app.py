"""SlideForge AI — agentic PowerPoint studio (Streamlit UI).

Run with:  streamlit run app.py
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:  # optional .env support
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from slide_agent import (
    SAFE_FONTS,
    SLIDE_TYPES,
    THEMES,
    AgentConfig,
    ConversationMemory,
    DeckChatAgent,
    DeckContent,
    LLMClient,
    SlideAgent,
    Theme,
    build_deck,
    get_theme,
    preview,
    theme_from_dict,
    theme_to_dict,
)
from slide_agent.models import DeckOutline, SlideOutline
from slide_agent.template_analyzer import describe_template, open_template

MEMORY_FILE = Path(__file__).parent / ".slideforge_memory.json"

st.set_page_config(
    page_title="SlideForge AI — Agentic Deck Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.6rem; }
      .sf-hero h1 { margin-bottom: 0.1rem; }
      .sf-hero p  { color: #6B7280; margin-top: 0; }
      .sf-chip { display:inline-block; padding:2px 10px; margin:0 6px 6px 0; border-radius:999px;
                 background:#EEF2FF; color:#4F46E5; font-size:12px; font-weight:600; }
      .sf-card { border:1px solid rgba(0,0,0,.09); border-radius:12px; padding:14px 16px; }
      div[data-testid="stFileUploader"] section { padding: 0.6rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1", "gpt-5", "gpt-5-mini", "o4-mini", "Custom…"]
TONES = ["Executive & crisp", "Storytelling", "Educational", "Persuasive / sales",
         "Technical deep-dive", "Inspirational"]
LANGS = ["English", "German", "Hindi", "French", "Spanish", "Same as brief"]

EXAMPLES = {
    "🏦 Bank AI strategy": "A 12-slide strategy deck for the executive board of a mid-size German bank "
                           "on adopting agentic AI across customer support, treasury and compliance — "
                           "covering opportunity sizing, use-case portfolio, operating model, risks and a 12-month roadmap.",
    "🚀 Startup pitch": "An investor pitch for 'FinPilot', an AI copilot that automates corporate treasury "
                        "operations. Problem, solution, product demo highlights, market size, business model, "
                        "traction, competition, team and a $3M seed ask.",
    "📚 Tech explainer": "An educational deck explaining how Retrieval-Augmented Generation (RAG) works for a "
                         "non-technical audience: why LLMs hallucinate, embeddings, vector search, the RAG "
                         "pipeline, evaluation, and when to use fine-tuning instead.",
    "📈 QBR review": "A quarterly business review for a SaaS company: ARR growth, churn, NRR, pipeline health, "
                     "product launches, customer wins, misses and priorities for next quarter.",
}


# ----------------------------------------------------------------------------- state
def init_state():
    if "memory" not in st.session_state:
        st.session_state.memory = ConversationMemory.load(MEMORY_FILE)
    defaults = {
        "outline_df": None,
        "deck_title": "",
        "deck_subtitle": "",
        "brief": st.session_state.memory.brief if "memory" in st.session_state else "",
        "pptx_bytes": None,
        "deck": None,             # live DeckContent — chat edits mutate this
        "deck_result": None,      # last full pipeline result (research notes, critique log)
        "gen_meta": {},
        "theme_dict": theme_to_dict(get_theme("aurora")),
        "template_bytes": None,
        "template_name": "",
        "template_info": None,
        "use_template": False,
        "design_rationale": "",
        "chat_changed": [],
        "persist_memory": True,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


init_state()
MEM: ConversationMemory = st.session_state.memory


def current_theme() -> Theme:
    return theme_from_dict(st.session_state.theme_dict)


def set_theme(theme: Theme):
    st.session_state.theme_dict = theme_to_dict(theme)


def save_memory():
    if st.session_state.persist_memory:
        try:
            MEM.brief = st.session_state.brief
            MEM.save(MEMORY_FILE)
        except OSError:
            pass


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name).strip()
    return re.sub(r"[\s]+", "_", name)[:60] or "slideforge_deck"


def rebuild_pptx() -> None:
    """Re-render the .pptx from the live deck + current design. No LLM cost."""
    deck = st.session_state.deck
    if deck is None:
        return
    st.session_state.pptx_bytes = build_deck(
        deck,
        theme=current_theme(),
        template_bytes=st.session_state.template_bytes if st.session_state.use_template else None,
        template_name=st.session_state.template_name,
        footer=st.session_state.get("footer_text", ""),
    )


def snapshot(label: str):
    if st.session_state.deck is not None:
        MEM.snapshot(st.session_state.deck, st.session_state.theme_dict, label)
        save_memory()


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("## 🎬 SlideForge AI")
    st.caption("An agent team that plans, writes, critiques and designs your deck.")

    st.markdown("#### 🔑 Your OpenAI key")
    api_key = st.text_input(
        "API key", value=os.environ.get("OPENAI_API_KEY", ""),
        type="password", placeholder="sk-…",
        help="Bring your own key. Used only for this session — never stored or logged.",
    )
    model_pick = st.selectbox("Model", MODELS, index=0,
                              help="gpt-4o-mini is fast & inexpensive; larger models write richer decks.")
    custom_model = ""
    if model_pick == "Custom…":
        custom_model = st.text_input("Custom model id", placeholder="e.g. llama-3.3-70b-versatile")
    with st.expander("⚙️ Advanced endpoint"):
        base_url = st.text_input(
            "Base URL (optional)", placeholder="https://api.groq.com/openai/v1",
            help="Any OpenAI-compatible endpoint: Groq, OpenRouter, Azure gateway, local vLLM/Ollama…",
        )
    creativity = st.slider("Creativity", 0.0, 1.0, 0.7, 0.05,
                           help="Higher = more adventurous copy. Mapped to model temperature.")

    st.divider()
    st.markdown("#### 🧠 Content")
    n_slides = st.slider("Slides", 5, 20, 10)
    audience = st.text_input("Audience", "Business executives")
    tone = st.selectbox("Tone", TONES)
    language = st.selectbox("Language", LANGS)
    st.session_state.footer_text = st.text_input("Footer (optional)", placeholder="Acme Corp · Confidential")

    with st.expander("🤖 Agent settings"):
        research_on = st.toggle("Researcher agent (fact sheet before writing)", value=True)
        critique_rounds = st.slider("Critique → revise rounds", 0, 2, 1,
                                    help="Each round the Critic reviews the deck and the Reviser fixes flagged slides.")
        seed_facts = st.text_area("Your facts & data (optional)", height=100,
                                  placeholder="Paste numbers, quotes or notes the deck MUST use…")
        extra_instructions = st.text_area("Extra style instructions (optional)", height=80,
                                          placeholder="e.g. cite frameworks by name, keep bullets under 10 words…")

    st.divider()
    st.markdown("#### 💾 Memory")
    st.session_state.persist_memory = st.toggle(
        "Remember across restarts", value=st.session_state.persist_memory,
        help=f"Saves preferences, chat history and versions to {MEMORY_FILE.name} (gitignored).",
    )
    st.caption(f"{len(MEM.preferences)} preference(s) · {len(MEM.turns)} chat turn(s) · "
               f"{len(MEM.versions)} version(s)")
    if MEM.preferences:
        with st.expander(f"📌 Learned preferences ({len(MEM.preferences)})"):
            for i, pref in enumerate(list(MEM.preferences)):
                pc1, pc2 = st.columns([6, 1])
                pc1.markdown(f"<small>{pref}</small>", unsafe_allow_html=True)
                if pc2.button("✕", key=f"forget_{i}", help="Forget this"):
                    MEM.forget(i); save_memory(); st.rerun()
    new_pref = st.text_input("Teach a preference", placeholder="e.g. never use the word 'leverage'")
    if new_pref:
        if MEM.remember([new_pref]):
            save_memory(); st.toast("Remembered ✓", icon="🧠"); st.rerun()
    if st.button("🗑️ Clear all memory", use_container_width=True):
        MEM.clear(); MEMORY_FILE.unlink(missing_ok=True); st.rerun()

model = (custom_model or model_pick).strip() if model_pick == "Custom…" else model_pick
key_ready = bool((api_key or "").strip())


def make_agent() -> SlideAgent:
    llm = LLMClient(api_key=api_key, model=model, base_url=base_url or None,
                    temperature=0.2 + 0.8 * creativity)
    cfg = AgentConfig(
        n_slides=n_slides, audience=audience, tone=tone, language=language,
        research=research_on, critique_rounds=critique_rounds,
        extra_instructions=extra_instructions or "", seed_facts=seed_facts or "",
    )
    return SlideAgent(llm, cfg, memory=MEM)


def outline_to_df(outline: DeckOutline) -> pd.DataFrame:
    return pd.DataFrame([{"Type": s.type, "Slide title": s.title, "Talking points / hints": s.hints}
                         for s in outline.slides])


def df_to_outline(df: pd.DataFrame) -> DeckOutline:
    slides = []
    for _, row in df.fillna("").iterrows():
        title = str(row.get("Slide title", "")).strip()
        hints = str(row.get("Talking points / hints", "")).strip()
        if not title and not hints:
            continue
        stype = str(row.get("Type", "bullets")).strip() or "bullets"
        slides.append(SlideOutline(type=stype if stype in SLIDE_TYPES else "bullets",
                                   title=title, hints=hints))
    return DeckOutline(deck_title=st.session_state.deck_title or "Untitled deck",
                       subtitle=st.session_state.deck_subtitle, slides=slides)


def generate(agent: SlideAgent, brief: str, outline: DeckOutline | None, auto_design: bool = False):
    t0 = time.time()
    with st.status("🤖 Agent team at work…", expanded=True) as status:
        prog = st.progress(0.0)
        lines = st.empty()
        history: list[str] = []

        def on_event(stage: str, msg: str, frac: float):
            history.append(f"• {msg}")
            lines.markdown("\n".join(history[-7:]))
            prog.progress(min(max(frac, 0.0), 1.0), text=msg)

        if auto_design:
            key = agent.pick_theme(brief, on_event)
            set_theme(get_theme(key))
            st.session_state.design_rationale = agent.design_rationale
            st.session_state.use_template = False

        result = agent.run(brief, on_event) if outline is None else agent.run_from_outline(brief, outline, on_event)

        on_event("build", "🏗️ Rendering .pptx…", 0.97)
        st.session_state.deck = result.deck
        rebuild_pptx()
        prog.progress(1.0, text="Done")
        status.update(label="✅ Deck ready", state="complete", expanded=False)

    st.session_state.deck_result = result
    st.session_state.outline_df = outline_to_df(result.outline)
    st.session_state.deck_title = result.deck.title
    st.session_state.deck_subtitle = result.deck.subtitle
    st.session_state.chat_changed = []
    st.session_state.gen_meta = {"seconds": round(time.time() - t0, 1), "model": model,
                                 "tokens": dict(agent.llm.usage)}
    MEM.brief = brief
    snapshot("Generated deck")
    st.toast("Deck generated 🎉", icon="✅")


# ----------------------------------------------------------------------------- header
st.markdown(
    '<div class="sf-hero"><h1>🎬 SlideForge AI</h1>'
    "<p>Brief in → an agent team plans, researches, writes, critiques — then you refine it by chatting.</p></div>",
    unsafe_allow_html=True,
)
st.markdown(
    '<span class="sf-chip">Planner</span><span class="sf-chip">Researcher</span>'
    '<span class="sf-chip">Writer</span><span class="sf-chip">Critic</span>'
    '<span class="sf-chip">Reviser</span><span class="sf-chip">Designer</span>'
    '<span class="sf-chip">Editor 💬</span><span class="sf-chip">🧠 Memory</span>',
    unsafe_allow_html=True,
)

if not key_ready:
    st.info("👋 **Welcome!** Paste your OpenAI API key in the sidebar to begin. "
            "Your key stays in this browser session only — bring your own key, bring your own template.",
            icon="🔑")

tabs = st.tabs(["**① Brief**", "**② Outline**", "**③ Deck**", "**④ Design Studio**", "**⑤ Chat with your deck**"])

# --------------------------------------------------------------- ① brief
with tabs[0]:
    st.markdown("##### Start from an example")
    cols = st.columns(len(EXAMPLES))
    for col, (label, text) in zip(cols, EXAMPLES.items()):
        if col.button(label, use_container_width=True):
            st.session_state.brief = text
            st.rerun()

    brief = st.text_area("Describe the deck you need", key="brief", height=190,
                         placeholder="What is the presentation about? Who is it for? What should it achieve?\n"
                                     "The more context you give, the sharper the deck.")

    c1, c2, c3 = st.columns([1.2, 1.6, 1.6])
    ready = key_ready and bool(brief.strip())
    if c1.button("🧭 Draft outline", disabled=not ready, use_container_width=True,
                 help="Planner (+ Researcher) propose an outline you can edit before writing."):
        try:
            agent = make_agent()
            with st.status("🧭 Planning…") as status:
                notes = agent.research(brief) if research_on else []
                outline = agent.plan(brief, notes)
                status.update(label=f"✅ Outline drafted — {len(outline.slides)} slides", state="complete")
            st.session_state.outline_df = outline_to_df(outline)
            st.session_state.deck_title = outline.deck_title
            st.session_state.deck_subtitle = outline.subtitle
            st.toast("Outline ready — see tab ② Outline", icon="🧭")
        except Exception as e:
            st.error(f"Outline failed: {e}")
    if c2.button("⚡ Auto-pilot: brief → deck", type="primary", disabled=not ready, use_container_width=True):
        try:
            generate(make_agent(), brief, None)
        except Exception as e:
            st.error(f"Generation failed: {e}")
    if c3.button("🎨 Auto-pilot + AI design", disabled=not ready, use_container_width=True,
                 help="The Designer agent also picks the visual system for your topic."):
        try:
            generate(make_agent(), brief, None, auto_design=True)
        except Exception as e:
            st.error(f"Generation failed: {e}")

# --------------------------------------------------------------- ② outline
with tabs[1]:
    if st.session_state.outline_df is None:
        st.caption("No outline yet — draft one from tab ① Brief, or build one from scratch below.")
        st.session_state.outline_df = pd.DataFrame(
            [{"Type": "title", "Slide title": "", "Talking points / hints": ""}])

    tc1, tc2 = st.columns([2.4, 1.6])
    st.session_state.deck_title = tc1.text_input("Deck title", st.session_state.deck_title)
    st.session_state.deck_subtitle = tc2.text_input("Subtitle", st.session_state.deck_subtitle)

    st.caption("✏️ Edit titles and hints, change slide types, add or delete rows, drag to reorder.")
    st.session_state.outline_df = st.data_editor(
        st.session_state.outline_df, num_rows="dynamic", use_container_width=True,
        column_config={
            "Type": st.column_config.SelectboxColumn("Type", options=SLIDE_TYPES, width="small"),
            "Slide title": st.column_config.TextColumn("Slide title", width="medium"),
            "Talking points / hints": st.column_config.TextColumn(
                "Talking points / hints", width="large",
                help="Guidance for the Writer agent — what must this slide convey?"),
        },
        key="outline_editor",
    )

    oc1, oc2, _ = st.columns([1.4, 1.8, 2])
    if oc1.button("🔄 Re-draft with AI", disabled=not (key_ready and st.session_state.brief.strip()),
                  use_container_width=True):
        try:
            agent = make_agent()
            outline = agent.plan(st.session_state.brief,
                                 agent.research(st.session_state.brief) if research_on else [])
            st.session_state.outline_df = outline_to_df(outline)
            st.session_state.deck_title = outline.deck_title
            st.session_state.deck_subtitle = outline.subtitle
            st.rerun()
        except Exception as e:
            st.error(f"Re-draft failed: {e}")
    if oc2.button("🚀 Generate from this outline", type="primary", disabled=not key_ready,
                  use_container_width=True):
        try:
            outline = df_to_outline(st.session_state.outline_df)
            if not outline.slides:
                st.warning("The outline is empty — add at least one slide.")
            else:
                generate(make_agent(), st.session_state.brief, outline)
        except Exception as e:
            st.error(f"Generation failed: {e}")

# --------------------------------------------------------------- ③ deck
with tabs[2]:
    deck: DeckContent | None = st.session_state.deck
    if deck is None:
        st.caption("Nothing generated yet. Use **⚡ Auto-pilot** on tab ①, or curate the outline on tab ②.")
    else:
        meta = st.session_state.gen_meta
        theme = current_theme()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Slides", len(deck.slides))
        m2.metric("Words", deck.word_count)
        m3.metric("Time", f"{meta.get('seconds', '–')} s")
        tk = meta.get("tokens", {})
        m4.metric("LLM calls", tk.get("calls", "–"),
                  help=f"≈ {tk.get('prompt_tokens', 0):,} prompt + {tk.get('completion_tokens', 0):,} completion tokens")

        st.download_button(
            f"⬇️ Download “{deck.title}.pptx”", data=st.session_state.pptx_bytes or b"",
            file_name=f"{sanitize_filename(deck.title)}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            type="primary", use_container_width=True,
        )
        design_label = st.session_state.template_name if st.session_state.use_template else theme.name
        st.caption(f"Model **{meta.get('model', model)}** · design **{design_label}**")

        zc1, zc2 = st.columns([1, 3])
        zoom = zc1.select_slider("Preview size", ["S", "M", "L"], value="M")
        scale = {"S": 0.34, "M": 0.46, "L": 0.62}[zoom]
        per_row = {"S": 4, "M": 3, "L": 2}[zoom]
        if st.session_state.use_template:
            zc2.info("🖼️ Template mode — the preview shows layout and content; your template's "
                     "own masters, logos and fonts are applied in the downloaded .pptx.", icon="ℹ️")

        components.html(
            preview.deck_html(deck, theme, st.session_state.get("footer_text", ""), scale,
                              highlight=st.session_state.chat_changed),
            height=preview.grid_height(len(deck.slides), scale, per_row), scrolling=True,
        )

        res = st.session_state.deck_result
        if res and res.research_notes:
            with st.expander("🔎 Researcher's fact sheet"):
                for n in res.research_notes:
                    st.markdown(f"- {n}")
        if res and res.critique_log:
            with st.expander("🧪 Critic → Reviser log"):
                for line in res.critique_log:
                    st.markdown(f"`{line}`")
        with st.expander("📝 Text & speaker notes"):
            for i, s in enumerate(deck.slides, start=1):
                st.markdown(f"**{i}. [{s.type}] {s.title or '(untitled)'}**")
                for b in s.bullets:
                    st.markdown(("    - " if b.startswith(">>") else "- ") + b.lstrip(">").strip())
                if s.notes:
                    st.caption(f"🗣️ {s.notes}")

# --------------------------------------------------------------- ④ design studio
with tabs[3]:
    theme = current_theme()
    st.markdown("##### 🎨 Design Studio — change the look any time, no re-writing required")

    if st.session_state.design_rationale:
        st.success(f"**Designer agent:** {st.session_state.design_rationale}", icon="🎨")

    dc1, dc2 = st.columns([1.15, 1])
    with dc1:
        st.markdown("**Live preview**")
        sample = st.session_state.deck.slides[0] if st.session_state.deck else None
        sample_idx = 0
        if st.session_state.deck and len(st.session_state.deck.slides) > 1:
            sample_idx = st.select_slider(
                "Slide", options=list(range(len(st.session_state.deck.slides))),
                value=min(2, len(st.session_state.deck.slides) - 1),
                format_func=lambda i: f"{i + 1}. {st.session_state.deck.slides[i].type}")
            sample = st.session_state.deck.slides[sample_idx]
        if sample is not None:
            components.html(
                preview.slides_html(st.session_state.deck, theme, [sample_idx],
                                    st.session_state.get("footer_text", ""), scale=0.62),
                height=int(preview.SLIDE_H * 0.62) + 60,
            )
        else:
            st.caption("Generate a deck to preview the design on real content.")
            components.html(preview.theme_gallery_html([theme], scale=0.62),
                            height=int(preview.SLIDE_H * 0.62) + 60)

    with dc2:
        st.markdown("**Design source**")
        src = st.radio("Design source", ["Built-in theme", "🖼️ My template", "🤖 Describe it to the Designer"],
                       label_visibility="collapsed",
                       index=1 if st.session_state.use_template else 0)

        if src == "Built-in theme":
            st.session_state.use_template = False
            keys = list(THEMES.keys())
            cur = theme.key if theme.key in keys else keys[0]
            pick = st.selectbox("Theme", keys, index=keys.index(cur),
                                format_func=lambda k: f"{THEMES[k].name} — {THEMES[k].tagline}")
            if st.button("Apply theme", use_container_width=True):
                set_theme(THEMES[pick]); st.session_state.design_rationale = ""
                rebuild_pptx(); snapshot(f"Theme → {THEMES[pick].name}"); st.rerun()

        elif src == "🖼️ My template":
            up = st.file_uploader("Upload .pptx / .potx", type=["pptx", "potx"],
                                  help="Masters, layouts, logos, colours and fonts are kept; existing slides cleared.")
            if up is not None:
                try:
                    info = describe_template(open_template(up.getvalue(), up.name))
                    st.session_state.template_bytes = up.getvalue()
                    st.session_state.template_name = up.name
                    st.session_state.template_info = info
                    st.session_state.use_template = True
                    st.success(f"✓ {len(info['layouts'])} layouts · {info['masters']} master(s) · "
                               f"{info['size_in'][0]}×{info['size_in'][1]}\" canvas")
                    if info["existing_slides"]:
                        st.caption(f"ℹ️ {info['existing_slides']} existing slide(s) cleared; branding kept.")
                    if st.button("Apply template", type="primary", use_container_width=True):
                        rebuild_pptx(); snapshot(f"Template → {up.name}"); st.rerun()
                except Exception as e:
                    st.error(f"Could not read template: {e}")
            elif st.session_state.template_name:
                st.info(f"Using **{st.session_state.template_name}**")
                if st.button("Stop using template", use_container_width=True):
                    st.session_state.use_template = False; rebuild_pptx(); st.rerun()

        else:
            st.session_state.use_template = False
            desc = st.text_area("Describe the look you want", height=90,
                                placeholder="e.g. a Magic Circle law firm — deep navy, warm gold accent, "
                                            "serif headings, very restrained")
            if st.button("🎨 Design it", type="primary", disabled=not (key_ready and desc.strip()),
                         use_container_width=True):
                try:
                    with st.status("🎨 Designer agent at work…", expanded=True) as status:
                        holder = st.empty()

                        def on_ev(stage, msg, frac):
                            holder.markdown(f"• {msg}")

                        agent = make_agent()
                        new_theme = agent.design_from_prompt(desc, base=theme, on_event=on_ev)
                        status.update(label=f"✅ Designed “{new_theme.name}”", state="complete")
                    set_theme(new_theme)
                    st.session_state.design_rationale = agent.design_rationale
                    rebuild_pptx(); snapshot(f"AI design → {new_theme.name}"); st.rerun()
                except Exception as e:
                    st.error(f"Design failed: {e}")

        with st.expander("🎛️ Fine-tune colours & fonts"):
            t = current_theme()
            cc1, cc2 = st.columns(2)
            picks = {}
            labels = [("primary", "Brand / title bg"), ("accent", "Accent"), ("secondary", "Secondary"),
                      ("bg", "Background"), ("surface", "Card surface"), ("text", "Text"), ("muted", "Muted text")]
            for i, (field, label) in enumerate(labels):
                col = cc1 if i % 2 == 0 else cc2
                picks[field] = col.color_picker(label, "#" + getattr(t, field), key=f"cp_{field}")
            fh = st.selectbox("Heading font", SAFE_FONTS,
                              index=SAFE_FONTS.index(t.heading_font) if t.heading_font in SAFE_FONTS else 0)
            fb = st.selectbox("Body font", SAFE_FONTS,
                              index=SAFE_FONTS.index(t.body_font) if t.body_font in SAFE_FONTS else 0)
            if st.button("Apply tweaks", use_container_width=True):
                tweaked = t.with_overrides(
                    key="custom", name="Custom", tagline="Hand-tuned palette",
                    heading_font=fh, body_font=fb,
                    **{f: v.lstrip("#").upper() for f, v in picks.items()},
                )
                tweaked = tweaked.with_overrides(
                    is_dark=(int(tweaked.bg[0:2], 16) * 0.2126 + int(tweaked.bg[2:4], 16) * 0.7152
                             + int(tweaked.bg[4:6], 16) * 0.0722) / 255 < 0.35)
                set_theme(tweaked); rebuild_pptx(); snapshot("Manual colour tweak"); st.rerun()

    st.divider()
    st.markdown("**Theme gallery** — click a name above to apply")
    components.html(preview.theme_gallery_html(list(THEMES.values()), current=theme.key, scale=0.3),
                    height=preview.grid_height(len(THEMES), 0.3, 4), scrolling=False)

    if MEM.versions:
        st.divider()
        st.markdown("**🕘 Version history** — every change is snapshotted")
        for i in range(len(MEM.versions) - 1, -1, -1):
            v = MEM.versions[i]
            vc1, vc2, vc3 = st.columns([3.2, 1.6, 1])
            vc1.markdown(f"**{v['label']}**")
            vc2.caption(time.strftime("%H:%M:%S", time.localtime(v["ts"])))
            if vc3.button("Restore", key=f"restore_{i}", use_container_width=True):
                restored = MEM.restore(i)
                if restored:
                    st.session_state.deck = restored["deck"]
                    if restored.get("theme"):
                        st.session_state.theme_dict = restored["theme"]
                    rebuild_pptx(); st.toast("Version restored", icon="🕘"); st.rerun()

# --------------------------------------------------------------- ⑤ chat
with tabs[4]:
    st.markdown("##### 💬 Talk to your deck — the Editor agent amends, adds, reorders or redesigns")

    if st.session_state.deck is None:
        st.info("Generate a deck first (tab ①), then come back and tell me what to change.", icon="💡")
    else:
        st.caption("Try: *“slide 3 is too wordy — cut to 4 bullets”* · *“add a competitor comparison after slide 5”* · "
                   "*“make the whole deck punchier and add numbers”* · *“make it dark and modern”* · *“delete the quote slide”*")

        hist = st.container(height=340)
        with hist:
            if not MEM.turns:
                st.caption("No messages yet — ask for a change below.")
            for t in MEM.turns:
                with st.chat_message("user" if t["role"] == "user" else "assistant"):
                    st.markdown(t["content"])
                    if t.get("actions"):
                        st.caption(" · ".join(t["actions"]))

        if st.session_state.chat_changed:
            st.markdown("**Updated slides**")
            components.html(
                preview.slides_html(st.session_state.deck, current_theme(),
                                    st.session_state.chat_changed[:4],
                                    st.session_state.get("footer_text", ""), scale=0.42),
                height=preview.grid_height(min(4, len(st.session_state.chat_changed)), 0.42, 3),
            )

        msg = st.chat_input("Tell the Editor agent what to change…", disabled=not key_ready)
        if msg:
            MEM.add_turn("user", msg)
            try:
                agent = make_agent()
                chat = DeckChatAgent(agent, MEM)
                with st.status("💬 Editor agent…", expanded=True) as status:
                    holder = st.empty()
                    prog = st.progress(0.0)

                    def on_ev(stage, msg_, frac):
                        holder.markdown(f"• {msg_}")
                        prog.progress(min(max(frac, 0.0), 1.0))

                    outcome = chat.handle(msg, st.session_state.deck, current_theme(), on_ev)
                    status.update(label="✅ Editor done", state="complete", expanded=False)

                st.session_state.deck = outcome.deck
                if outcome.design_changed and outcome.theme is not None:
                    set_theme(outcome.theme)
                    st.session_state.design_rationale = agent.design_rationale
                if outcome.deck_changed or outcome.design_changed:
                    rebuild_pptx()
                    snapshot(outcome.actions[0] if outcome.actions else "Chat edit")
                st.session_state.chat_changed = outcome.changed
                MEM.add_turn("assistant", outcome.reply, outcome.actions)
                if outcome.remembered:
                    st.toast(f"Remembered: {outcome.remembered[0][:50]}", icon="🧠")
                save_memory()
                st.rerun()
            except Exception as e:
                MEM.add_turn("assistant", f"⚠️ Something went wrong: {e}")
                st.error(f"Editor failed: {e}")

st.divider()
st.caption("SlideForge AI · agentic deck generation · bring your own key, bring your own template. "
           "Keys are held in session memory only.")
