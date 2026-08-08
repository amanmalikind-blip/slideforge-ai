"""Conversational deck editor — talk to your deck and it changes.

The chat agent works in two phases:

1. **Route** — one LLM call reads the message, the conversation history, the standing
   preferences and a map of the current deck, then returns a short reply plus a list of
   structured *operations* (and anything worth remembering long-term).
2. **Execute** — the operations run deterministically in Python, delegating the actual
   writing to the existing Writer/Reviser agents. Nothing is applied that the router
   did not explicitly ask for, so "what's on slide 4?" never mutates the deck.

Supported ops: edit_slide, add_slide, delete_slide, move_slide, set_type, restyle_all,
change_theme, custom_design, set_title, regenerate, none.
"""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .agent import EventCallback, SlideAgent, _noop
from .memory import ConversationMemory
from .models import SLIDE_TYPES, DeckContent, DeckOutline, SlideContent, SlideOutline
from .themes import THEMES, Theme, get_theme

OPS_DOC = """
Available operations (emit only what the user actually asked for):
- {"op":"edit_slide","target":<slide number or title>,"instruction":"what to change"}
- {"op":"add_slide","position":<slide number to insert AT, or null for end>,"type":"<slide type>","instruction":"what it should say"}
- {"op":"delete_slide","target":<slide number or title>}
- {"op":"move_slide","target":<slide number or title>,"position":<new slide number>}
- {"op":"set_type","target":<slide number or title>,"type":"<slide type>"}   # re-render as a different layout
- {"op":"restyle_all","instruction":"a change to apply to EVERY slide"}      # expensive, use only for deck-wide edits
- {"op":"set_title","title":"new deck title","subtitle":"new subtitle"}
- {"op":"change_theme","theme":"<one of: aurora, boardroom, skyline, minimal, terra, noir>"}
- {"op":"custom_design","instruction":"describe the look to design from scratch"}
- {"op":"regenerate","instruction":"a fresh brief — rebuilds the WHOLE deck, use only if clearly asked"}
"""


@dataclass
class ChatOutcome:
    reply: str
    deck: DeckContent
    theme: Optional[Theme] = None
    actions: List[str] = field(default_factory=list)
    changed: List[int] = field(default_factory=list)
    deck_changed: bool = False
    design_changed: bool = False
    remembered: List[str] = field(default_factory=list)


class DeckChatAgent:
    def __init__(self, agent: SlideAgent, memory: ConversationMemory):
        self.agent = agent
        self.memory = memory
        agent.memory = memory  # so every downstream prompt inherits standing preferences

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def deck_map(deck: DeckContent) -> str:
        if not deck.slides:
            return "(the deck is empty)"
        lines = []
        for i, s in enumerate(deck.slides, start=1):
            gist = (s.title or s.quote or "")[:60]
            detail = ""
            if s.bullets:
                detail = f" — {len(s.bullets)} bullets"
            elif s.kpis:
                detail = f" — KPIs: {', '.join(k.value for k in s.kpis[:3])}"
            elif s.steps:
                detail = f" — steps: {' → '.join(s.steps[:4])}"
            elif s.table and s.table.headers:
                detail = f" — table: {', '.join(s.table.headers[:4])}"
            lines.append(f"{i}. [{s.type}] {gist}{detail}")
        return "\n".join(lines)

    @staticmethod
    def _resolve(deck: DeckContent, target: Any) -> Optional[int]:
        """Slide number (1-based) or title text → 0-based index."""
        if target is None:
            return None
        if isinstance(target, bool):
            return None
        if isinstance(target, (int, float)):
            idx = int(target) - 1
            return idx if 0 <= idx < len(deck.slides) else None
        text = str(target).strip()
        if text.isdigit():
            idx = int(text) - 1
            return idx if 0 <= idx < len(deck.slides) else None
        titles = [s.title or "" for s in deck.slides]
        match = difflib.get_close_matches(text, titles, n=1, cutoff=0.55)
        if match:
            return titles.index(match[0])
        low = text.lower()
        for i, t in enumerate(titles):
            if low in (t or "").lower():
                return i
        return None

    def _outline_from_deck(self, deck: DeckContent) -> DeckOutline:
        return DeckOutline(
            deck_title=deck.title,
            subtitle=deck.subtitle,
            slides=[SlideOutline(type=s.type, title=s.title, hints="") for s in deck.slides],
        )

    # ------------------------------------------------------------------ routing
    def route(self, message: str, deck: DeckContent, theme: Optional[Theme]) -> Dict[str, Any]:
        theme_line = f"{theme.name} (bg {theme.bg}, primary {theme.primary}, accent {theme.accent})" if theme else "none yet"
        system = (
            "You are the Editor Agent of SlideForge — a conversational presentation editor. "
            "The user talks to you about their deck; you reply briefly and decide which "
            "operations to run. Be decisive: if the user asks for a change, emit the operation "
            "rather than asking permission. If they only ask a question, emit no operations and "
            "answer in 'reply'. Resolve references like 'that slide', 'the last one' or 'the KPI "
            "slide' using the deck map and conversation history. "
            f"Valid slide types: {', '.join(SLIDE_TYPES)}.\n{OPS_DOC}\n"
            "'remember' should capture only DURABLE style preferences worth applying to future "
            "slides (e.g. 'bullets max 8 words', 'always use British spelling'), never one-off edits. "
            'Return ONLY JSON: {"reply": str, "actions": [...], "remember": [str]}'
        )
        user = (
            f"Deck title: {deck.title}\nCurrent design: {theme_line}\n"
            f"Deck map:\n{self.deck_map(deck)}\n"
            f"{self.memory.prefs_block()}\n"
            f"Recent conversation:\n{self.memory.recent(6)}\n\n"
            f"User's new message: {message}"
        )
        return self.agent.llm.complete_json(system, user, temperature=0.3)

    # ------------------------------------------------------------------ execution
    def handle(self, message: str, deck: DeckContent, theme: Optional[Theme] = None,
               on_event: EventCallback = _noop) -> ChatOutcome:
        on_event("chat", "💬 Editor agent: understanding your request…", 0.1)
        try:
            routed = self.route(message, deck, theme)
        except Exception as e:
            return ChatOutcome(reply=f"I couldn't parse that request ({e}). Could you rephrase?", deck=deck)

        reply = str(routed.get("reply", "")).strip() or "Done."
        actions = routed.get("actions") or []
        if isinstance(actions, dict):
            actions = [actions]
        remembered = self.memory.remember([str(r) for r in (routed.get("remember") or [])])

        out = ChatOutcome(reply=reply, deck=deck, theme=theme, remembered=remembered)
        total = max(1, len(actions))
        for n, action in enumerate(actions):
            if not isinstance(action, dict):
                continue
            op = str(action.get("op", "none")).lower().strip()
            frac = 0.15 + 0.75 * (n / total)
            try:
                self._apply(op, action, out, on_event, frac)
            except Exception as e:
                out.actions.append(f"⚠️ '{op}' failed: {e}")
        out.changed = sorted(set(i for i in out.changed if 0 <= i < len(out.deck.slides)))
        on_event("chat", "✅ Done", 1.0)
        return out

    def _apply(self, op: str, a: Dict[str, Any], out: ChatOutcome,
               on_event: EventCallback, frac: float) -> None:
        deck = out.deck

        if op == "edit_slide":
            idx = self._resolve(deck, a.get("target"))
            if idx is None:
                out.actions.append("⚠️ Couldn't find that slide"); return
            instr = str(a.get("instruction", "")).strip() or "improve this slide"
            on_event("chat", f"✏️ Rewriting slide {idx + 1}…", frac)
            deck.slides[idx] = self.agent.revise_slide(deck, idx, instr)
            out.actions.append(f"Edited slide {idx + 1}: {instr[:60]}")
            out.changed.append(idx); out.deck_changed = True

        elif op == "add_slide":
            stype = str(a.get("type", "bullets")).lower().strip()
            if stype not in SLIDE_TYPES:
                stype = "bullets"
            pos_raw = a.get("position")
            pos = len(deck.slides) if pos_raw in (None, "", "end") else max(0, int(pos_raw) - 1)
            pos = min(pos, len(deck.slides))
            instr = str(a.get("instruction", "")).strip() or "a new slide"
            on_event("chat", f"➕ Writing a new {stype} slide at position {pos + 1}…", frac)
            outline = self._outline_from_deck(deck)
            outline.slides.insert(pos, SlideOutline(type=stype, title=instr[:70], hints=instr))
            new_slide = self.agent.write_slide(outline, pos)
            deck.slides.insert(pos, new_slide)
            out.actions.append(f"Added {stype} slide at position {pos + 1}")
            out.changed = [i + 1 if i >= pos else i for i in out.changed] + [pos]
            out.deck_changed = True

        elif op == "delete_slide":
            idx = self._resolve(deck, a.get("target"))
            if idx is None:
                out.actions.append("⚠️ Couldn't find that slide"); return
            title = deck.slides[idx].title
            deck.slides.pop(idx)
            out.actions.append(f"Deleted slide {idx + 1} “{title}”")
            out.changed = [i - 1 if i > idx else i for i in out.changed if i != idx]
            out.deck_changed = True

        elif op == "move_slide":
            idx = self._resolve(deck, a.get("target"))
            new_pos = a.get("position")
            if idx is None or new_pos in (None, ""):
                out.actions.append("⚠️ Couldn't work out the move"); return
            dest = max(0, min(int(new_pos) - 1, len(deck.slides) - 1))
            deck.slides.insert(dest, deck.slides.pop(idx))
            out.actions.append(f"Moved slide {idx + 1} → position {dest + 1}")
            out.changed.append(dest); out.deck_changed = True

        elif op == "set_type":
            idx = self._resolve(deck, a.get("target"))
            stype = str(a.get("type", "")).lower().strip()
            if idx is None or stype not in SLIDE_TYPES:
                out.actions.append("⚠️ Couldn't change that layout"); return
            on_event("chat", f"🔀 Re-rendering slide {idx + 1} as {stype}…", frac)
            outline = self._outline_from_deck(deck)
            outline.slides[idx].type = stype
            outline.slides[idx].hints = (
                f"Same message as before, re-expressed as a '{stype}' slide. "
                f"Existing content: {json.dumps(deck.slides[idx].model_dump(), ensure_ascii=False)[:900]}"
            )
            deck.slides[idx] = self.agent.write_slide(outline, idx)
            out.actions.append(f"Slide {idx + 1} is now a {stype} slide")
            out.changed.append(idx); out.deck_changed = True

        elif op == "restyle_all":
            instr = str(a.get("instruction", "")).strip()
            if not instr:
                return
            for i in range(len(deck.slides)):
                on_event("chat", f"🎯 Restyling slide {i + 1}/{len(deck.slides)}…",
                         frac + 0.6 * (i / max(1, len(deck.slides))) / 10)
                try:
                    deck.slides[i] = self.agent.revise_slide(deck, i, instr)
                    out.changed.append(i)
                except Exception:
                    continue
            out.actions.append(f"Restyled all {len(deck.slides)} slides: {instr[:60]}")
            out.deck_changed = True

        elif op == "set_title":
            if a.get("title"):
                deck.title = str(a["title"])
            if a.get("subtitle") is not None:
                deck.subtitle = str(a["subtitle"])
            for i, s in enumerate(deck.slides):
                if s.type == "title":
                    s.title, s.subtitle = deck.title, deck.subtitle or s.subtitle
                    out.changed.append(i)
            out.actions.append(f"Deck title → “{deck.title}”")
            out.deck_changed = True

        elif op == "change_theme":
            key = str(a.get("theme", "")).lower().strip()
            if key not in THEMES:
                out.actions.append(f"⚠️ Unknown theme '{key}'"); return
            out.theme = get_theme(key)
            self.agent.design_rationale = f"Switched on request to {out.theme.name}."
            out.actions.append(f"Design → {out.theme.name}")
            out.design_changed = True

        elif op == "custom_design":
            instr = str(a.get("instruction", "")).strip()
            if not instr:
                return
            out.theme = self.agent.design_from_prompt(instr, base=out.theme, on_event=on_event)
            out.actions.append(f"Designed a new look: {out.theme.name}")
            out.design_changed = True

        elif op == "regenerate":
            brief = str(a.get("instruction", "")).strip() or self.memory.brief
            on_event("chat", "♻️ Rebuilding the whole deck…", frac)
            result = self.agent.run(brief, on_event)
            out.deck = result.deck
            self.memory.brief = brief
            out.actions.append(f"Regenerated the deck ({len(result.deck.slides)} slides)")
            out.changed = list(range(len(result.deck.slides)))
            out.deck_changed = True
