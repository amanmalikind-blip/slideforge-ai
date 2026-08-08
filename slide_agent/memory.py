"""Persistent memory for a deck session.

Three kinds of memory, all serialisable to a single JSON file:

- **Conversation memory** — the running dialogue with the chat editor, so follow-ups like
  "make that one shorter too" resolve against what was just discussed.
- **Preference memory** — durable style rules the user has expressed ("always keep bullets
  under 8 words", "we say 'colleagues', never 'employees'"). Fed into every agent prompt.
- **Version memory** — snapshots of the deck + theme after each change, so any edit is undoable.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import DeckContent

MAX_VERSIONS = 15
MAX_TURNS = 60


class ConversationMemory:
    def __init__(self, brief: str = ""):
        self.brief: str = brief
        self.turns: List[Dict[str, Any]] = []
        self.preferences: List[str] = []
        self.versions: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ dialogue
    def add_turn(self, role: str, content: str, actions: Optional[List[str]] = None) -> None:
        self.turns.append({
            "role": role,
            "content": content,
            "actions": actions or [],
            "ts": time.time(),
        })
        if len(self.turns) > MAX_TURNS:
            self.turns = self.turns[-MAX_TURNS:]

    def recent(self, n: int = 8) -> str:
        """Compact transcript for prompting."""
        if not self.turns:
            return "(no prior conversation)"
        lines = []
        for t in self.turns[-n:]:
            who = "User" if t["role"] == "user" else "Assistant"
            lines.append(f"{who}: {t['content'][:400]}")
            if t.get("actions"):
                lines.append(f"  (actions taken: {'; '.join(t['actions'][:4])})")
        return "\n".join(lines)

    # ------------------------------------------------------------------ preferences
    def remember(self, items: List[str]) -> List[str]:
        """Store new durable preferences; returns the ones actually added."""
        added = []
        for raw in items or []:
            pref = str(raw).strip()
            if not pref or len(pref) > 200:
                continue
            # de-dupe case-insensitively
            if any(pref.lower() == p.lower() for p in self.preferences):
                continue
            self.preferences.append(pref)
            added.append(pref)
        self.preferences = self.preferences[-25:]
        return added

    def forget(self, index: int) -> None:
        if 0 <= index < len(self.preferences):
            self.preferences.pop(index)

    def prefs_block(self) -> str:
        if not self.preferences:
            return ""
        return ("\nStanding user preferences (learned in earlier turns — always honour these):\n- "
                + "\n- ".join(self.preferences))

    # ------------------------------------------------------------------ versions
    def snapshot(self, deck: DeckContent, theme_dict: Optional[Dict[str, Any]], label: str) -> None:
        self.versions.append({
            "label": label,
            "ts": time.time(),
            "deck": deck.model_dump(),
            "theme": theme_dict,
        })
        if len(self.versions) > MAX_VERSIONS:
            self.versions = self.versions[-MAX_VERSIONS:]

    def restore(self, index: int) -> Optional[Dict[str, Any]]:
        """Returns {'deck': DeckContent, 'theme': dict|None} for the chosen version."""
        if not (0 <= index < len(self.versions)):
            return None
        v = self.versions[index]
        return {"deck": DeckContent.model_validate(v["deck"]), "theme": v.get("theme")}

    # ------------------------------------------------------------------ persistence
    def to_dict(self) -> Dict[str, Any]:
        return {
            "brief": self.brief,
            "turns": self.turns,
            "preferences": self.preferences,
            "versions": self.versions,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationMemory":
        mem = cls(brief=data.get("brief", ""))
        mem.turns = data.get("turns", [])
        mem.preferences = data.get("preferences", [])
        mem.versions = data.get("versions", [])
        return mem

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ConversationMemory":
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return cls()

    def clear(self) -> None:
        self.turns.clear()
        self.preferences.clear()
        self.versions.clear()
