"""SlideForge AI — agentic PowerPoint studio (Streamlit UI).

Run with:  streamlit run app.py
"""
from __future__ import annotations

import io
import re
import time

import pandas as pd
import streamlit as st

try:  # optional .env support
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os

from slide_agent import (
    AgentConfig,
    LLMClient,
    SLIDE_TYPES,
    SlideAgent,
    THEMES,
    build_deck,
    get_theme,
)
from slide_agent.models import DeckOutline, SlideOutline
from slide_agent.template_analyzer import describe_template, open_template

# ----------------------------------------------------------------------------- page setup
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
      div[data-testid="stSidebarHeader"] { padding-bottom: 0; }
      .sf-hero h1 { margin-bottom: 0.1rem; }
      .sf-hero p  { color: #6B7280; margin-top: 0; }
      .sf-chip { display:inline-block; padding:2px 10px; margin:0 6px 6px 0; border-radius:999px;
                 background:#EEF2FF; color:#4F46E5; font-size:12px; font-weight:600; }
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


def init_state():
    defaults = {
        "outline_df": None,
        "deck_title": "",
        "deck_subtitle": "",
        "brief": "",
        "pptx_bytes": None,
        "deck_result": None,
        "gen_meta": {},
        "template_info": None,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


init_state()


def swatch_html(theme) -> str:
    chips = "".join(
        f'<span style="display:inline-block;width:26px;height:26px;border-radius:8px;'
        f'margin-right:7px;background:#{c};border:1px solid rgba(0,0,0,.12)"></span>'
        for c in (theme.primary, theme.secondary, theme.accent, theme.surface, theme.text)
    )
    return (f'<div style="margin:6px 0 2px">{chips}</div>'
            f'<div style="font-size:12px;opacity:.75">{theme.tagline}</div>')


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name).strip()
    return re.sub(r"[\s]+", "_", name)[:60] or "slideforge_deck"


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
    st.markdown("#### 🎨 Design")
    design_mode = st.radio(
        "Design source", ["Built-in theme", "🖼️ My template", "🤖 Let the agent pick"],
        label_visibility="collapsed",
    )
    selected_theme_key, template_file = None, None
    if design_mode == "Built-in theme":
        selected_theme_key = st.selectbox(
            "Theme", list(THEMES.keys()), format_func=lambda k: THEMES[k].name,
        )
        st.markdown(swatch_html(THEMES[selected_theme_key]), unsafe_allow_html=True)
    elif design_mode == "🖼️ My template":
        template_file = st.file_uploader(
            "Upload .pptx / .potx", type=["pptx", "potx"],
            help="Your masters, layouts, colours and fonts are kept; existing slides are cleared.",
        )
        if template_file is not None:
            try:
                info = describe_template(open_template(template_file.getvalue(), template_file.name))
                st.session_state.template_info = info
                st.success(
                    f"✓ {len(info['layouts'])} layouts · {info['masters']} master(s) · "
                    f"{info['size_in'][0]}×{info['size_in'][1]}\" canvas"
                )
                if info["existing_slides"]:
                    st.caption(f"ℹ️ {info['existing_slides']} existing slide(s) will be cleared; branding is kept.")
            except Exception as e:
                st.error(f"Could not read template: {e}")
                template_file = None
    else:
        st.caption("The Designer agent will study your brief and pick the best-fitting theme.")

    st.divider()
    st.markdown("#### 🧠 Content")
    n_slides = st.slider("Slides", 5, 20, 10)
    audience = st.text_input("Audience", "Business executives")
    tone = st.selectbox("Tone", TONES)
    language = st.selectbox("Language", LANGS)
    footer_text = st.text_input("Footer (optional)", placeholder="Acme Corp · Confidential")

    with st.expander("🤖 Agent settings"):
        research_on = st.toggle("Researcher agent (fact sheet before writing)", value=True)
        critique_rounds = st.slider("Critique → revise rounds", 0, 2, 1,
                                    help="Each round the Critic reviews the deck and the Reviser fixes flagged slides.")
        seed_facts = st.text_area(
            "Your facts & data (optional)", height=100,
            placeholder="Paste numbers, quotes or notes the deck MUST use…",
        )
        extra_instructions = st.text_area(
            "Extra style instructions (optional)", height=80,
            placeholder="e.g. cite frameworks by name, keep it under 10 words per bullet…",
        )

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
    return SlideAgent(llm, cfg)


def outline_to_df(outline: DeckOutline) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Type": s.type, "Slide title": s.title, "Talking points / hints": s.hints}
         for s in outline.slides]
    )


def df_to_outline(df: pd.DataFrame) -> DeckOutline:
    slides = []
    for _, row in df.fillna("").iterrows():
        title = str(row.get("Slide title", "")).strip()
        stype = str(row.get("Type", "bullets")).strip() or "bullets"
        if not title and not str(row.get("Talking points / hints", "")).strip():
            continue
        if stype not in SLIDE_TYPES:
            stype = "bullets"
        slides.append(SlideOutline(type=stype, title=title,
                                   hints=str(row.get("Talking points / hints", "")).strip()))
    return DeckOutline(
        deck_title=st.session_state.deck_title or "Untitled deck",
        subtitle=st.session_state.deck_subtitle, slides=slides,
    )


def resolve_design(brief: str, agent: SlideAgent, on_event):
    """Returns (theme, template_bytes, template_name, chosen_key_for_caption)."""
    if design_mode == "🖼️ My template" and template_file is not None:
        return None, template_file.getvalue(), template_file.name, "your template"
    if design_mode == "🤖 Let the agent pick":
        key = agent.pick_theme(brief, on_event)
        return get_theme(key), None, "", THEMES[key].name
    key = selected_theme_key or "aurora"
    return get_theme(key), None, "", THEMES[key].name


def generate(agent: SlideAgent, brief: str, outline: DeckOutline | None):
    """Run the pipeline with live progress and stash results in session state."""
    t0 = time.time()
    with st.status("🤖 Agent team at work…", expanded=True) as status:
        prog = st.progress(0.0)
        lines = st.empty()
        history: list[str] = []

        def on_event(stage: str, msg: str, frac: float):
            history.append(f"• {msg}")
            lines.markdown("\n".join(history[-6:]))
            prog.progress(min(max(frac, 0.0), 1.0), text=msg)

        theme, tpl_bytes, tpl_name, design_label = resolve_design(brief, agent, on_event)
        if outline is None:
            result = agent.run(brief, on_event)
        else:
            result = agent.run_from_outline(brief, outline, on_event)

        on_event("build", "🏗️ Rendering .pptx…", 0.97)
        pptx_bytes = build_deck(result.deck, theme=theme, template_bytes=tpl_bytes,
                                template_name=tpl_name, footer=footer_text)
        prog.progress(1.0, text="Done")
        status.update(label="✅ Deck ready", state="complete", expanded=False)

    st.session_state.pptx_bytes = pptx_bytes
    st.session_state.deck_result = result
    st.session_state.outline_df = outline_to_df(result.outline)
    st.session_state.deck_title = result.deck.title
    st.session_state.deck_subtitle = result.deck.subtitle
    st.session_state.gen_meta = {
        "seconds": round(time.time() - t0, 1),
        "model": model,
        "design": design_label,
        "tokens": dict(agent.llm.usage),
    }
    st.toast("Deck generated 🎉", icon="✅")


# ----------------------------------------------------------------------------- main area
st.markdown(
    '<div class="sf-hero"><h1>🎬 SlideForge AI</h1>'
    "<p>Brief in → an agent team plans, researches, writes, critiques — polished .pptx out.</p></div>",
    unsafe_allow_html=True,
)
st.markdown(
    '<span class="sf-chip">Planner</span><span class="sf-chip">Researcher</span>'
    '<span class="sf-chip">Writer</span><span class="sf-chip">Critic</span>'
    '<span class="sf-chip">Reviser</span><span class="sf-chip">Designer</span>',
    unsafe_allow_html=True,
)

if not key_ready:
    st.info("👋 **Welcome!** Paste your OpenAI API key in the sidebar to begin. "
            "Your key stays in this browser session only — bring your own key, bring your own template.",
            icon="🔑")

tab_brief, tab_outline, tab_generate = st.tabs(["**① Brief**", "**② Outline**", "**③ Generate & Download**"])

# --------------------------------------------------------------- tab 1: brief
with tab_brief:
    st.markdown("##### Start from an example")
    cols = st.columns(len(EXAMPLES))
    for col, (label, text) in zip(cols, EXAMPLES.items()):
        if col.button(label, use_container_width=True):
            st.session_state.brief = text
            st.rerun()

    brief = st.text_area(
        "Describe the deck you need",
        key="brief", height=190,
        placeholder="What is the presentation about? Who is it for? What should it achieve?\n"
                    "The more context you give, the sharper the deck.",
    )

    c1, c2, _ = st.columns([1.2, 1.6, 2.5])
    draft_clicked = c1.button("🧭 Draft outline", disabled=not (key_ready and brief.strip()),
                              use_container_width=True,
                              help="Planner (+ Researcher) propose an outline you can edit before writing.")
    auto_clicked = c2.button("⚡ Auto-pilot: brief → deck", type="primary",
                             disabled=not (key_ready and brief.strip()), use_container_width=True,
                             help="Run the whole agent pipeline end-to-end in one go.")

    if draft_clicked:
        try:
            agent = make_agent()
            with st.status("🧭 Planning…", expanded=False) as status:
                notes = agent.research(brief) if research_on else []
                outline = agent.plan(brief, notes)
                status.update(label=f"✅ Outline drafted — {len(outline.slides)} slides", state="complete")
            st.session_state.outline_df = outline_to_df(outline)
            st.session_state.deck_title = outline.deck_title
            st.session_state.deck_subtitle = outline.subtitle
            st.toast("Outline ready — see tab ② Outline", icon="🧭")
        except Exception as e:
            st.error(f"Outline failed: {e}")

    if auto_clicked:
        try:
            generate(make_agent(), brief, outline=None)
        except Exception as e:
            st.error(f"Generation failed: {e}")

# --------------------------------------------------------------- tab 2: outline
with tab_outline:
    if st.session_state.outline_df is None:
        st.caption("No outline yet — draft one from tab ① Brief, or add rows below from scratch.")
        st.session_state.outline_df = pd.DataFrame(
            [{"Type": "title", "Slide title": "", "Talking points / hints": ""}]
        )

    tcol1, tcol2 = st.columns([2.4, 1.6])
    st.session_state.deck_title = tcol1.text_input("Deck title", st.session_state.deck_title)
    st.session_state.deck_subtitle = tcol2.text_input("Subtitle", st.session_state.deck_subtitle)

    st.caption("✏️ Edit titles and hints, change slide types, add or delete rows, drag to reorder.")
    edited = st.data_editor(
        st.session_state.outline_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Type": st.column_config.SelectboxColumn("Type", options=SLIDE_TYPES, width="small"),
            "Slide title": st.column_config.TextColumn("Slide title", width="medium"),
            "Talking points / hints": st.column_config.TextColumn(
                "Talking points / hints", width="large",
                help="Guidance for the Writer agent — what must this slide convey?"),
        },
        key="outline_editor",
    )
    st.session_state.outline_df = edited

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
    if oc2.button("🚀 Generate from this outline", type="primary",
                  disabled=not key_ready, use_container_width=True):
        try:
            outline = df_to_outline(st.session_state.outline_df)
            if not outline.slides:
                st.warning("The outline is empty — add at least one slide.")
            else:
                generate(make_agent(), st.session_state.brief, outline)
        except Exception as e:
            st.error(f"Generation failed: {e}")

# --------------------------------------------------------------- tab 3: generate & download
with tab_generate:
    if st.session_state.pptx_bytes is None:
        st.caption("Nothing generated yet. Use **⚡ Auto-pilot** on tab ①, or curate the outline on tab ② "
                   "and hit **🚀 Generate from this outline**.")
    else:
        result = st.session_state.deck_result
        meta = st.session_state.gen_meta
        deck = result.deck

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Slides", len(deck.slides))
        m2.metric("Words", deck.word_count)
        m3.metric("Time", f"{meta.get('seconds', '–')} s")
        tokens = meta.get("tokens", {})
        m4.metric("LLM calls", tokens.get("calls", "–"),
                  help=f"≈ {tokens.get('prompt_tokens', 0):,} prompt + "
                       f"{tokens.get('completion_tokens', 0):,} completion tokens")

        st.download_button(
            f"⬇️ Download “{deck.title}.pptx”",
            data=st.session_state.pptx_bytes,
            file_name=f"{sanitize_filename(deck.title)}.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            type="primary", use_container_width=True,
        )
        st.caption(f"Model **{meta.get('model')}** · design **{meta.get('design')}**")

        if result.research_notes:
            with st.expander("🔎 Researcher's fact sheet"):
                for n in result.research_notes:
                    st.markdown(f"- {n}")
        if result.critique_log:
            with st.expander("🧪 Critic → Reviser log"):
                for line in result.critique_log:
                    st.markdown(f"`{line}`")

        st.markdown("##### 👀 Slide-by-slide preview")
        for i, s in enumerate(deck.slides, start=1):
            with st.expander(f"**{i}. [{s.type}] {s.title or '(untitled)'}**"):
                if s.subtitle:
                    st.caption(s.subtitle)
                if s.quote:
                    st.markdown(f"> *{s.quote}*  \n> — {s.attribution}")
                for b in s.bullets:
                    st.markdown(("    - " if b.startswith(">>") else "- ") + b.lstrip(">").strip())
                if s.left_bullets or s.right_bullets:
                    lc, rc = st.columns(2)
                    lc.markdown(f"**{s.left_title}**")
                    for b in s.left_bullets:
                        lc.markdown(f"- {b}")
                    rc.markdown(f"**{s.right_title}**")
                    for b in s.right_bullets:
                        rc.markdown(f"- {b}")
                if s.kpis:
                    kcols = st.columns(len(s.kpis))
                    for kc, k in zip(kcols, s.kpis):
                        kc.metric(k.label, k.value)
                if s.steps:
                    st.markdown(" → ".join(f"**{step}**" for step in s.steps))
                if s.table and s.table.headers:
                    st.table(pd.DataFrame(s.table.rows, columns=s.table.headers))
                if s.notes:
                    st.caption(f"🗣️ Speaker notes: {s.notes}")

st.divider()
st.caption("SlideForge AI · agentic deck generation · bring your own key, bring your own template. "
           "Keys are held in session memory only.")
