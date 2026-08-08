"""SlideForge agentic pipeline.

A deck is produced by a team of specialised agents, each with its own system prompt,
coordinated by `SlideAgent`:

    Brief ──▶ Researcher ─▶ Planner ─▶ Writer (per slide) ─▶ Critic ⇄ Reviser ─▶ DeckContent
                    │                                            │
                    └────────── Designer (auto theme pick) ──────┘

- Researcher  : pulls angles, frameworks and defensible figures from model knowledge.
- Planner     : turns the brief into a typed outline (title/section/kpi/process/... mix).
- Designer    : optionally picks the best built-in theme for the topic & audience.
- Writer      : writes each slide as strict JSON matching the SlideContent schema.
- Critic      : scores the deck and files concrete, slide-level issues.
- Reviser     : rewrites only the flagged slides (reflection loop, configurable rounds).

Every step reports progress through an `on_event(stage, message, fraction)` callback so
the UI (Streamlit or notebook) can render live status.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from pydantic import ValidationError

from .llm import LLMClient
from .models import (
    Critique,
    DeckContent,
    DeckOutline,
    SLIDE_TYPES,
    SlideContent,
    SlideOutline,
)
from .themes import THEMES

EventCallback = Callable[[str, str, float], None]


def _noop(stage: str, message: str, fraction: float) -> None:  # pragma: no cover
    pass


@dataclass
class AgentConfig:
    n_slides: int = 10
    audience: str = "Business executives"
    tone: str = "Executive & crisp"
    language: str = "English"
    research: bool = True
    critique_rounds: int = 1
    extra_instructions: str = ""
    seed_facts: str = ""  # user-pasted data/notes the writer must prefer over model memory


@dataclass
class AgentResult:
    deck: DeckContent
    outline: DeckOutline
    research_notes: List[str] = field(default_factory=list)
    critique_log: List[str] = field(default_factory=list)
    theme_choice: Optional[str] = None


class SlideAgent:
    def __init__(self, llm: LLMClient, config: Optional[AgentConfig] = None):
        self.llm = llm
        self.config = config or AgentConfig()

    # ------------------------------------------------------------------ shared prompt bits
    def _lang_rule(self) -> str:
        lang = self.config.language
        if lang.lower().startswith("same"):
            return "Write all deck text in the same language as the brief."
        return f"Write all deck text in {lang}."

    def _style_rules(self) -> str:
        c = self.config
        extra = f"\nAdditional instructions from the user: {c.extra_instructions}" if c.extra_instructions else ""
        return (
            f"Audience: {c.audience}. Tone: {c.tone}. {self._lang_rule()}{extra}"
        )

    # ------------------------------------------------------------------ researcher
    def research(self, brief: str, on_event: EventCallback = _noop) -> List[str]:
        on_event("research", "Researcher agent: gathering angles, frameworks & figures…", 0.05)
        system = (
            "You are the Research Agent of SlideForge, a presentation intelligence system. "
            "From your knowledge, produce a compact fact sheet a slide writer can rely on: "
            "sharp angles, named frameworks, market context, and concrete figures. "
            "Prefix genuinely uncertain or estimated figures with '≈'. Never invent citations. "
            'Return ONLY JSON: {"notes": ["...", "..."]} with 6-10 items, each under 30 words.'
        )
        user = f"Topic brief:\n{brief}\n\n{self._style_rules()}"
        try:
            data = self.llm.complete_json(system, user, temperature=0.4)
            notes = [str(n) for n in data.get("notes", [])][:10]
        except Exception:
            notes = []  # research is best-effort; never blocks the pipeline
        return notes

    # ------------------------------------------------------------------ planner
    def plan(self, brief: str, research_notes: Optional[List[str]] = None,
             on_event: EventCallback = _noop) -> DeckOutline:
        on_event("plan", "Planner agent: structuring the deck…", 0.12)
        c = self.config
        notes_block = ""
        if research_notes:
            notes_block = "\nResearch notes you may draw on:\n- " + "\n- ".join(research_notes)
        system = (
            "You are the Planning Agent of SlideForge, an elite presentation strategist. "
            "Design a slide-by-slide outline with a strong narrative arc "
            "(hook → context → insight → evidence → action). "
            f"Allowed slide types: {', '.join(SLIDE_TYPES)}. "
            "Rules: the first slide MUST be type 'title' and the last MUST be 'closing'. "
            "Vary layouts: use kpi, process, comparison, table or quote wherever the content "
            "supports it; never place more than two consecutive 'bullets' slides. "
            "Use 'section' dividers only for decks of 10+ slides. "
            "'hints' = 1-2 sentences telling the writer exactly what the slide must convey. "
            'Return ONLY JSON: {"deck_title": str, "subtitle": str, '
            '"slides": [{"type": str, "title": str, "hints": str}]}'
        )
        user = (
            f"Brief:\n{brief}\n\nProduce exactly {c.n_slides} slides. "
            f"{self._style_rules()}{notes_block}"
        )
        data = self.llm.complete_json(system, user)
        outline = self._coerce_outline(data)
        on_event("plan", f"Outline ready: “{outline.deck_title}” · {len(outline.slides)} slides", 0.2)
        return outline

    def _coerce_outline(self, data: dict) -> DeckOutline:
        slides = []
        for s in data.get("slides", []):
            stype = str(s.get("type", "bullets")).strip().lower()
            if stype not in SLIDE_TYPES:
                stype = "bullets"
            slides.append(SlideOutline(type=stype, title=str(s.get("title", "")).strip(),
                                       hints=str(s.get("hints", "")).strip()))
        if slides and slides[0].type != "title":
            slides.insert(0, SlideOutline(type="title", title=str(data.get("deck_title", "")), hints=""))
        if slides and slides[-1].type != "closing":
            slides.append(SlideOutline(type="closing", title="Thank you", hints="Wrap up with next steps."))
        return DeckOutline(
            deck_title=str(data.get("deck_title", "Untitled deck")).strip() or "Untitled deck",
            subtitle=str(data.get("subtitle", "")).strip(),
            slides=slides,
        )

    # ------------------------------------------------------------------ designer
    def pick_theme(self, brief: str, on_event: EventCallback = _noop) -> str:
        on_event("design", "Designer agent: choosing a visual system…", 0.22)
        catalog = "\n".join(f"- {t.key}: {t.name} — {t.tagline}" for t in THEMES.values())
        system = (
            "You are the Design Agent of SlideForge. Pick the single most fitting theme for "
            "this presentation, considering topic, audience and formality. "
            'Return ONLY JSON: {"theme": "<key>", "why": "<one sentence>"}'
        )
        user = f"Brief:\n{brief}\n\nAudience: {self.config.audience}\n\nTheme catalog:\n{catalog}"
        try:
            data = self.llm.complete_json(system, user, temperature=0.2)
            key = str(data.get("theme", "")).lower().strip()
            if key in THEMES:
                on_event("design", f"Designer picked “{THEMES[key].name}” — {data.get('why', '')}", 0.24)
                return key
        except Exception:
            pass
        return "aurora"

    # ------------------------------------------------------------------ writer
    _WRITER_FIELD_GUIDE = """
Field guide per slide type (include ONLY the relevant fields, plus "notes" always):
- title:      title, subtitle
- section:    title, subtitle (a short kicker line)
- bullets:    title, subtitle (optional), bullets (3-6)
- two_column: title, left_title, left_bullets (2-4), right_title, right_bullets (2-4)
- comparison: title, left_title, left_bullets (2-4), right_title, right_bullets (2-4)
- quote:      quote, attribution
- kpi:        title, kpis (2-4 of {"value": "42%", "label": "what it measures"}), bullets (0-2 context)
- process:    title, steps (3-6 short phrases), bullets (0-2 context)
- table:      title, table {"headers": [2-5], "rows": [2-6 rows]}
- closing:    title, subtitle, bullets (0-3 next steps / contact)
"""

    def write_slide(self, outline: DeckOutline, index: int,
                    research_notes: Optional[List[str]] = None) -> SlideContent:
        so = outline.slides[index]
        deck_map = "\n".join(
            f"{i + 1}. [{s.type}] {s.title}" for i, s in enumerate(outline.slides)
        )
        notes_block = ""
        if research_notes:
            notes_block = "\nResearch notes (use when relevant):\n- " + "\n- ".join(research_notes)
        seed = f"\nUser-provided facts/data (authoritative, prefer over your memory):\n{self.config.seed_facts}" if self.config.seed_facts else ""
        system = (
            "You are the Writer Agent of SlideForge. Write world-class slide copy: specific, "
            "concrete and scannable. No filler words, no 'in today's world'. "
            "Bullets ≤ 12 words; prefix a bullet with '>>' to make it a sub-bullet. "
            "Prefer real numbers, named tools/frameworks and vivid verbs. "
            "Speaker notes: 2-4 conversational sentences that ADD to the slide, not repeat it. "
            f"{self._style_rules()}\n{self._WRITER_FIELD_GUIDE}\n"
            "Return ONLY a JSON object for this one slide."
        )
        user = (
            f"Deck title: {outline.deck_title}\nFull deck outline:\n{deck_map}\n"
            f"{notes_block}{seed}\n\n"
            f"Now write slide {index + 1}: type='{so.type}', working title='{so.title}'.\n"
            f"Slide intent: {so.hints or 'derive from the outline'}\n"
            'JSON schema: {"type": str, "title": str, "subtitle": str, "bullets": [], '
            '"left_title": str, "left_bullets": [], "right_title": str, "right_bullets": [], '
            '"quote": str, "attribution": str, "kpis": [{"value","label"}], "steps": [], '
            '"table": {"headers": [], "rows": [[]]}, "notes": str}'
        )
        data = self.llm.complete_json(system, user)
        sc = self._coerce_slide(data, fallback_title=so.title)
        sc.type = so.type  # the outline (possibly user-edited) is authoritative
        return sc

    def _coerce_slide(self, data: dict, fallback_title: str = "") -> SlideContent:
        try:
            sc = SlideContent.model_validate(data)
        except ValidationError:
            # Salvage the common fields rather than failing the whole run.
            safe = {k: v for k, v in data.items() if k in SlideContent.model_fields}
            for key in ("bullets", "left_bullets", "right_bullets", "steps"):
                if key in safe and isinstance(safe[key], list):
                    safe[key] = [str(x) for x in safe[key]]
                elif key in safe:
                    safe.pop(key)
            if "kpis" in safe and not isinstance(safe["kpis"], list):
                safe.pop("kpis")
            if "table" in safe and not isinstance(safe["table"], dict):
                safe.pop("table")
            try:
                sc = SlideContent.model_validate(safe)
            except ValidationError:
                sc = SlideContent(title=fallback_title or "Slide")
        if not sc.title:
            sc.title = fallback_title
        return sc

    def write_deck(self, outline: DeckOutline, research_notes: Optional[List[str]] = None,
                   on_event: EventCallback = _noop) -> DeckContent:
        deck = DeckContent(title=outline.deck_title, subtitle=outline.subtitle)
        n = max(1, len(outline.slides))
        for i in range(len(outline.slides)):
            so = outline.slides[i]
            frac = 0.25 + 0.5 * (i / n)
            on_event("write", f"Writer agent: slide {i + 1}/{n} — “{so.title}”", frac)
            deck.slides.append(self.write_slide(outline, i, research_notes))
        return deck

    # ------------------------------------------------------------------ critic + reviser
    def critique(self, deck: DeckContent, on_event: EventCallback = _noop) -> Critique:
        on_event("critique", "Critic agent: reviewing the full deck…", 0.8)
        compact = json.dumps(deck.model_dump(), ensure_ascii=False)[:14000]
        system = (
            "You are the Critic Agent of SlideForge, a ruthless presentation editor. "
            "Review the deck JSON for: weak or generic titles, redundant slides, vague bullets, "
            "bullets over 14 words, missing concrete numbers, monotonous structure, and a weak close. "
            "Only report issues genuinely worth fixing — an empty list is a valid answer. "
            'Return ONLY JSON: {"score": 1-10, "issues": [{"index": <0-based slide index>, '
            '"problem": str, "fix": "<precise instruction for the rewrite>"}]} with at most 4 issues.'
        )
        try:
            data = self.llm.complete_json(system, f"Deck JSON:\n{compact}", temperature=0.3)
            issues = data.get("issues", [])
            crit = Critique(
                score=int(data.get("score", 7)),
                issues=[i for i in (self._coerce_issue(x) for x in issues) if i is not None],
            )
        except Exception:
            crit = Critique(score=7, issues=[])
        return crit

    @staticmethod
    def _coerce_issue(x: dict):
        from .models import CritiqueIssue
        try:
            idx = int(x.get("index", -1))
        except (TypeError, ValueError):
            return None
        if idx < 0:
            return None
        return CritiqueIssue(index=idx, problem=str(x.get("problem", "")), fix=str(x.get("fix", "")))

    def revise_slide(self, deck: DeckContent, index: int, fix: str) -> SlideContent:
        sc = deck.slides[index]
        system = (
            "You are the Reviser Agent of SlideForge. Rewrite the given slide applying the "
            "editor's instruction exactly, keeping the same slide type and JSON schema. "
            f"{self._style_rules()}\nReturn ONLY the corrected slide JSON object."
        )
        user = (
            f"Slide JSON:\n{json.dumps(sc.model_dump(), ensure_ascii=False)}\n\n"
            f"Editor's instruction: {fix}"
        )
        data = self.llm.complete_json(system, user)
        fixed = self._coerce_slide(data, fallback_title=sc.title)
        fixed.type = sc.type
        return fixed

    def refine(self, deck: DeckContent, on_event: EventCallback = _noop) -> tuple[DeckContent, List[str]]:
        log: List[str] = []
        for round_no in range(self.config.critique_rounds):
            crit = self.critique(deck, on_event)
            log.append(f"Round {round_no + 1}: score {crit.score}/10, {len(crit.issues)} issue(s)")
            if not crit.issues:
                on_event("critique", f"Critic satisfied (score {crit.score}/10) — no changes needed", 0.9)
                break
            for j, issue in enumerate(crit.issues):
                if 0 <= issue.index < len(deck.slides):
                    on_event(
                        "revise",
                        f"Reviser agent: fixing slide {issue.index + 1} — {issue.problem[:70]}",
                        0.82 + 0.12 * (round_no + j / max(1, len(crit.issues))) / max(1, self.config.critique_rounds),
                    )
                    try:
                        deck.slides[issue.index] = self.revise_slide(deck, issue.index, issue.fix)
                        log.append(f"  ✓ slide {issue.index + 1}: {issue.problem}")
                    except Exception as e:  # keep the original slide on failure
                        log.append(f"  ✗ slide {issue.index + 1} revision failed: {e}")
        return deck, log

    # ------------------------------------------------------------------ orchestration
    def run(self, brief: str, on_event: EventCallback = _noop,
            auto_theme: bool = False) -> AgentResult:
        """Full pipeline from a text brief."""
        notes = self.research(brief, on_event) if self.config.research else []
        outline = self.plan(brief, notes, on_event)
        theme_choice = self.pick_theme(brief, on_event) if auto_theme else None
        deck = self.write_deck(outline, notes, on_event)
        deck, log = self.refine(deck, on_event)
        on_event("done", "Deck content complete", 0.96)
        return AgentResult(deck=deck, outline=outline, research_notes=notes,
                           critique_log=log, theme_choice=theme_choice)

    def run_from_outline(self, brief: str, outline: DeckOutline, on_event: EventCallback = _noop,
                         auto_theme: bool = False) -> AgentResult:
        """Pipeline starting from a (possibly user-edited) outline."""
        notes = self.research(brief, on_event) if (self.config.research and brief) else []
        theme_choice = self.pick_theme(brief or outline.deck_title, on_event) if auto_theme else None
        deck = self.write_deck(outline, notes, on_event)
        deck, log = self.refine(deck, on_event)
        on_event("done", "Deck content complete", 0.96)
        return AgentResult(deck=deck, outline=outline, research_notes=notes,
                           critique_log=log, theme_choice=theme_choice)
