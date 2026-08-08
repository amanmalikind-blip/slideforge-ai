"""Pydantic data models describing a deck: outline (planning stage) and content (writing stage)."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# The slide archetypes the builder knows how to render.
SlideType = Literal[
    "title",        # opening slide
    "section",      # section divider
    "bullets",      # classic talking-points slide
    "two_column",   # two side-by-side content columns
    "comparison",   # A vs B comparison cards
    "quote",        # big pull-quote
    "kpi",          # 2-4 headline stats
    "process",      # step-by-step chevron flow
    "table",        # data table
    "closing",      # thank-you / call-to-action
]

SLIDE_TYPES: List[str] = [
    "title", "section", "bullets", "two_column", "comparison",
    "quote", "kpi", "process", "table", "closing",
]


class SlideOutline(BaseModel):
    """One row of the deck outline produced by the Planner agent (editable by the user)."""
    type: SlideType = "bullets"
    title: str = ""
    hints: str = Field(default="", description="What this slide should convey (guidance for the Writer agent)")


class DeckOutline(BaseModel):
    """The full outline: the contract between the Planner and the Writer."""
    deck_title: str = "Untitled deck"
    subtitle: str = ""
    slides: List[SlideOutline] = Field(default_factory=list)


class KPI(BaseModel):
    value: str = ""
    label: str = ""


class TableSpec(BaseModel):
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)


class SlideContent(BaseModel):
    """Fully written content for a single slide. Only the fields relevant to `type` are used."""
    type: SlideType = "bullets"
    title: str = ""
    subtitle: str = ""
    bullets: List[str] = Field(default_factory=list, description="Prefix a bullet with '>>' to mark it as a sub-bullet")
    left_title: str = ""
    left_bullets: List[str] = Field(default_factory=list)
    right_title: str = ""
    right_bullets: List[str] = Field(default_factory=list)
    quote: str = ""
    attribution: str = ""
    kpis: List[KPI] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    table: Optional[TableSpec] = None
    notes: str = Field(default="", description="Speaker notes")


class DeckContent(BaseModel):
    """The finished deck, ready for the builder."""
    title: str = "Untitled deck"
    subtitle: str = ""
    slides: List[SlideContent] = Field(default_factory=list)

    @property
    def word_count(self) -> int:
        n = 0
        for s in self.slides:
            for field in (s.title, s.subtitle, s.quote, s.attribution, s.notes,
                          s.left_title, s.right_title):
                n += len(field.split())
            for lst in (s.bullets, s.left_bullets, s.right_bullets, s.steps):
                n += sum(len(x.split()) for x in lst)
            for k in s.kpis:
                n += len(k.value.split()) + len(k.label.split())
            if s.table:
                n += sum(len(h.split()) for h in s.table.headers)
                n += sum(len(c.split()) for r in s.table.rows for c in r)
        return n


class CritiqueIssue(BaseModel):
    index: int = 0
    problem: str = ""
    fix: str = ""


class Critique(BaseModel):
    score: int = 7
    issues: List[CritiqueIssue] = Field(default_factory=list)
