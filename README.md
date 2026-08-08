# 🎬 SlideForge AI — Agentic Deck Studio

**Brief in → an agent team plans, researches, writes, critiques — a polished `.pptx` out.**

SlideForge is an agentic AI presentation generator: a team of specialised LLM agents
(Planner, Researcher, Writer, Critic, Reviser, Designer) collaborate over the OpenAI API to
produce best-in-class slide decks. Use it through a flexible **Streamlit studio** or a
**Jupyter notebook** — with **bring-your-own-key** and **bring-your-own-template** built in.

```
Brief ──▶ Researcher ─▶ Planner ─▶ Writer (per slide) ─▶ Critic ⇄ Reviser ─▶ Builder ─▶ .pptx
                │                                            │
                └────────── Designer (auto theme pick) ──────┘
```

## ✨ Features

| | |
|---|---|
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
4. **③ Generate & Download** — watch the agents work, preview every slide, download the `.pptx`.

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
├── app.py                          # Streamlit studio (3-step flow, live agent progress)
├── slide_agent/
│   ├── agent.py                    # Agent team + orchestration (plan/research/write/critique/revise)
│   ├── llm.py                      # Resilient OpenAI client (BYO key, JSON mode w/ fallbacks)
│   ├── models.py                   # Pydantic schemas: outline, slide content, critique
│   ├── builder.py                  # python-pptx renderer (theme mode + template mode)
│   ├── themes.py                   # Built-in design systems + theme-from-template
│   └── template_analyzer.py        # .potx→.pptx conversion, OOXML theme extraction, layout scoring
├── notebooks/slide_agent_playground.ipynb
├── templates/                      # drop your corporate templates here
├── .streamlit/config.toml
├── requirements.txt
└── .env.example
```

## ☁️ Deploy on Streamlit Community Cloud

1. Push this repo to GitHub.
2. In [share.streamlit.io](https://share.streamlit.io), point a new app at `app.py`.
3. No server-side key needed — every user brings their own key in the sidebar.
   (Optionally set `OPENAI_API_KEY` in app *Secrets* to pre-fill it for yourself.)

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
