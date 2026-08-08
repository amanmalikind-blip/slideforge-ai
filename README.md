# 🎬 SlideForge AI — Agentic Deck Studio

**Brief in → an agent team plans, researches, writes, critiques — a polished `.pptx` out.**

SlideForge is an agentic AI presentation generator: a team of specialised LLM agents
(Planner, Researcher, Writer, Critic, Reviser, Designer) collaborate over the OpenAI API to
produce best-in-class slide decks. Use it through a flexible **Streamlit studio** or a
**Jupyter notebook** — with **bring-your-own-key** and **bring-your-own-template** built in.

```
Brief ──▶ Researcher ─▶ Planner ─▶ Writer (per slide) ─▶ Critic ⇄ Reviser ─▶ Builder ─▶ .pptx
                │                                            │                   ▲
                └────────── Designer (theme / bespoke) ───────┘                  │
                                                                                 │
        You ──▶ 💬 Editor agent ──▶ edit · add · delete · move · re-layout ───────┘
                     ▲                restyle · redesign · regenerate
                     └── 🧠 Memory: conversation + standing preferences + version history
```

## ✨ Features

| | |
|---|---|
| 💬 **Chat with your deck** | Refine by conversation: *"slide 3 is too wordy — cut to 4 bullets"*, *"add a competitor comparison after slide 5"*, *"make it dark and modern"*. The Editor agent routes your message into structured operations (edit / add / delete / move / re-layout / restyle / redesign) and runs them. Questions never mutate the deck. |
| 🧠 **Persistent memory** | Remembers the conversation, learns **standing preferences** ("bullets max 8 words", "never say 'leverage'") and feeds them into every agent prompt. Snapshots every change so any edit is one click from undo. Survives restarts. |
| 🎨 **Visible Designer + Design Studio** | Watch the Designer agent work and read *why* it chose a look. Then change the design any time — swap themes, hand-tune every colour and font, or describe what you want (*"a Magic Circle law firm — navy, gold, serif"*) and it designs a bespoke system. Re-skinning costs **zero** LLM calls. |
| 👀 **Live slide preview** | Pixel-faithful HTML rendering of every slide right in the browser (1 pt of PowerPoint = 1 px), so you see the design before downloading. |
| 🤖 **Agentic pipeline** | Six cooperating agents with a self-reflection loop: the Critic scores the deck and files slide-level issues, the Reviser rewrites only what's flagged (0–2 rounds, configurable). |
| 🔑 **Bring your own key** | Paste your OpenAI key in the sidebar — held in session memory only, never stored. Also reads `OPENAI_API_KEY` / `.env`. |
| 🌐 **Any OpenAI-compatible endpoint** | Optional base URL: Groq, OpenRouter, Azure gateways, local vLLM/Ollama — plus a custom model id field. |
| 🎨 **Best-in-class themes** | Six hand-tuned design systems (Aurora, Boardroom, Skyline, Minimal Ink, Terra, Noir Neon) with full colour + type systems, or let the **Designer agent** pick one for your topic. |
| 🖼️ **Bring your own template** | Upload a corporate `.pptx`/`.potx`: masters, layouts, logos, colours and fonts are kept; the deck is written *into* your branding. Colours/fonts are extracted from the OOXML theme so even custom-drawn slides match. |
| 🧱 **10 slide archetypes** | title, section, bullets, two-column, comparison, quote, KPI cards, process chevrons, data table, closing — the Planner mixes them for visual variety. |
| ✏️ **Editable outline grid** | Review and reshape the Planner's outline (retitle, retype, reorder, add/delete) before a single slide is written. |
| 📓 **Notebook playground** | Drive the same pipeline from Python: `notebooks/slide_agent_playground.ipynb`. |
| 🗣️ **Speaker notes** | Every slide ships with conversational presenter notes. |
| 📊 **Full transparency** | Researcher fact sheet, critique log, token usage and per-stage live progress in the UI. |

## 🚀 Quickstart

```bash
git clone <your-repo-url> slideforge-ai
cd slideforge-ai
pip install -r requirements.txt
streamlit run app.py
```

Then in the app:

1. **🔑 Key** — paste your OpenAI API key in the sidebar (or `cp .env.example .env` and fill it in).
2. **① Brief** — describe the deck (or click an example), then **⚡ Auto-pilot** for end-to-end,
   or **🧭 Draft outline** if you want to curate first.
3. **② Outline** — edit titles, types and hints in the grid.
4. **③ Deck** — watch the agents work, see every slide rendered live, download the `.pptx`.
5. **④ Design Studio** — change the look any time: theme gallery, colour/font tuning,
   your own template, or describe a design and let the Designer build it. Restore any earlier version.
6. **⑤ Chat** — tell the Editor agent what to change and watch the affected slides update.

### Notebook

```bash
jupyter lab notebooks/slide_agent_playground.ipynb
```

### As a library

```python
from slide_agent import create_presentation

pptx_bytes, result = create_presentation(
    "Investor pitch for an AI treasury copilot",
    api_key="sk-...", model="gpt-4o-mini",
    n_slides=10, tone="Persuasive / sales", auto_theme=True,
)
open("pitch.pptx", "wb").write(pptx_bytes)
```

## 🏗️ Repository layout

```
├── app.py                          # Streamlit studio (5 tabs, live agent progress)
├── slide_agent/
│   ├── agent.py                    # Agent team + orchestration (plan/research/write/critique/revise/design)
│   ├── conversation.py             # 💬 Editor agent: message → structured ops → deck edits
│   ├── memory.py                   # 🧠 conversation, standing preferences, version snapshots
│   ├── preview.py                  # 👀 pixel-faithful HTML slide rendering (1 pt = 1 px)
│   ├── llm.py                      # Resilient OpenAI client (BYO key, JSON mode w/ fallbacks)
│   ├── models.py                   # Pydantic schemas: outline, slide content, critique
│   ├── builder.py                  # python-pptx renderer (theme mode + template mode)
│   ├── themes.py                   # Built-in design systems + theme-from-template / from-spec
│   └── template_analyzer.py        # .potx→.pptx conversion, OOXML theme extraction, layout scoring
├── notebooks/slide_agent_playground.ipynb
├── templates/                      # drop your corporate templates here
├── .streamlit/config.toml
├── requirements.txt
└── .env.example
```

### Talking to the Editor agent

| You say | What happens |
|---|---|
| "slide 3 is too wordy — 4 bullets max" | `edit_slide` → Reviser rewrites slide 3 only |
| "add a competitor comparison after slide 5" | `add_slide` → Writer drafts it, indices shift |
| "turn the roadmap into a process flow" | `set_type` → same message, new layout |
| "make the whole deck punchier, add numbers" | `restyle_all` → every slide revised |
| "make it dark and modern" | `custom_design` → Designer invents a palette |
| "what's on slide 4?" | answered — **nothing is changed** |

References like *"that slide"* or *"the KPI one"* resolve against the conversation history and a
live map of the deck; slides can be targeted by number **or** by title (fuzzy-matched).

## ☁️ Deploy on Streamlit Community Cloud

The repo is deploy-ready — no code changes needed.

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. **Create app** → **Deploy a public app from GitHub**.
3. Repository `amanmalikind-blip/slideforge-ai`, branch `main`, main file **`app.py`**.
4. **Deploy**. First build takes 2–4 minutes while dependencies install.

**No server-side API key is required** — every visitor brings their own in the sidebar.

> ⚠️ **Don't put your own `OPENAI_API_KEY` in Secrets on a *public* app.** The app pre-fills
> the key field from secrets, so every visitor would be spending *your* credit. Secrets are
> only appropriate for a private app or a self-hosted deploy.

### What changes when hosted

Community Cloud runs **one process for all visitors**. Session state is per-visitor, but the
filesystem is shared — so the app detects the hosted environment (`/mount/src`) and keeps
memory **in-session only**, never writing preferences, chat history or deck content to the
shared disk. Locally it is single-user, so disk persistence stays on and survives restarts.

Also worth knowing on the free tier: **1 GB RAM** per app (template uploads are capped at
25 MB in `.streamlit/config.toml` to stay well inside it), and apps **sleep after inactivity** —
the first visit after a nap takes a few seconds to wake, and wakes with empty memory.

## 🔒 Security notes

- API keys live only in Streamlit session state / process memory — never written to disk, never logged.
- `.gitignore` excludes `.env` and `.streamlit/secrets.toml`.
- Generated decks and the `output/` folder stay local.

## 🗺️ Roadmap ideas

- Image slides (DALL·E / gpt-image) and icon packs
- Chart rendering from data tables (native PPT charts)
- Multi-deck batch mode & PDF export
- RAG over user documents so decks cite your own material

---

*Built with Streamlit · OpenAI · python-pptx · Pydantic. MIT-licensed — use it, fork it, ship it.*
