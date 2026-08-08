"""SlideForge AI — agentic PowerPoint generation.

High-level usage:

    from slide_agent import create_presentation
    pptx_bytes, result = create_presentation(
        "Pitch deck for an AI-powered treasury analytics startup",
        api_key="sk-...", model="gpt-4o-mini", theme="boardroom", n_slides=10,
    )
    open("deck.pptx", "wb").write(pptx_bytes)
"""
from __future__ import annotations

from typing import Optional, Tuple

from .agent import AgentConfig, AgentResult, SlideAgent
from .builder import build_deck
from .conversation import ChatOutcome, DeckChatAgent
from .llm import LLMClient
from .memory import ConversationMemory
from .models import (
    DeckContent,
    DeckOutline,
    SLIDE_TYPES,
    SlideContent,
    SlideOutline,
)
from .preview import deck_html, slide_html, slides_html, theme_gallery_html
from .themes import (
    DEFAULT_THEME_KEY,
    SAFE_FONTS,
    THEMES,
    Theme,
    get_theme,
    theme_from_dict,
    theme_from_spec,
    theme_to_dict,
)

__version__ = "1.1.0"

__all__ = [
    "AgentConfig", "AgentResult", "SlideAgent", "LLMClient",
    "DeckChatAgent", "ChatOutcome", "ConversationMemory",
    "DeckContent", "DeckOutline", "SlideContent", "SlideOutline", "SLIDE_TYPES",
    "THEMES", "Theme", "get_theme", "DEFAULT_THEME_KEY", "SAFE_FONTS",
    "theme_from_dict", "theme_to_dict", "theme_from_spec",
    "deck_html", "slide_html", "slides_html", "theme_gallery_html",
    "build_deck", "create_presentation", "__version__",
]


def create_presentation(
    brief: str,
    api_key: Optional[str] = None,
    model: str = "gpt-4o-mini",
    base_url: Optional[str] = None,
    theme: str = DEFAULT_THEME_KEY,
    template_bytes: Optional[bytes] = None,
    template_name: str = "",
    footer: str = "",
    on_event=None,
    auto_theme: bool = False,
    **config,
) -> Tuple[bytes, AgentResult]:
    """One-call pipeline: brief → agent team → .pptx bytes."""
    llm = LLMClient(api_key=api_key, model=model, base_url=base_url,
                    temperature=config.pop("temperature", 0.7))
    agent = SlideAgent(llm, AgentConfig(**config))
    cb = on_event or (lambda stage, msg, frac: None)
    result = agent.run(brief, cb, auto_theme=auto_theme)
    chosen = get_theme(result.theme_choice or theme)
    data = build_deck(result.deck, theme=chosen, template_bytes=template_bytes,
                      template_name=template_name, footer=footer)
    cb("build", "Deck rendered to .pptx", 1.0)
    return data, result
