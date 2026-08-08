"""Best-in-class built-in design systems, plus support for themes extracted from user templates.

Every colour is a hex string like "4F46E5" (no leading '#'; the builder converts to RGBColor).
Fonts are limited to faces that ship with Windows/Office so decks open pixel-faithful anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Optional


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    tagline: str
    # Colour system
    bg: str        # slide background
    surface: str   # card / panel background
    text: str      # primary text
    muted: str     # secondary text
    primary: str   # brand colour (title slides, table headers)
    secondary: str # supporting brand colour (decorative shapes)
    accent: str    # highlight colour (bullets, KPI values, underlines)
    # Type system
    heading_font: str
    body_font: str
    is_dark: bool = False

    def with_overrides(self, **kwargs) -> "Theme":
        return replace(self, **kwargs)


THEMES: Dict[str, Theme] = {
    "aurora": Theme(
        key="aurora", name="Aurora", tagline="Modern tech — indigo, violet & cyan on white",
        bg="FFFFFF", surface="F3F4FF", text="1A1B2E", muted="6B7280",
        primary="4F46E5", secondary="7C3AED", accent="06B6D4",
        heading_font="Segoe UI", body_font="Segoe UI",
    ),
    "boardroom": Theme(
        key="boardroom", name="Boardroom", tagline="Executive corporate — deep navy with a gold accent",
        bg="FFFFFF", surface="F7F5F0", text="1F2A44", muted="64748B",
        primary="14213D", secondary="1F3A5F", accent="C9A227",
        heading_font="Georgia", body_font="Calibri",
    ),
    "skyline": Theme(
        key="skyline", name="Skyline", tagline="Consulting classic — confident blues, amber highlights",
        bg="FFFFFF", surface="EEF4FB", text="0F2B46", muted="5B7186",
        primary="0E5AA7", secondary="1379D1", accent="F59E0B",
        heading_font="Arial", body_font="Arial",
    ),
    "minimal": Theme(
        key="minimal", name="Minimal Ink", tagline="Editorial monochrome with a single red stroke",
        bg="FFFFFF", surface="F5F5F5", text="111111", muted="737373",
        primary="111111", secondary="404040", accent="E11D48",
        heading_font="Segoe UI Semibold", body_font="Segoe UI",
    ),
    "terra": Theme(
        key="terra", name="Terra", tagline="Warm & organic — espresso, clay and forest on cream",
        bg="FBF7F0", surface="F1E8DA", text="3E2F23", muted="8A7A6A",
        primary="7C4A2D", secondary="A0623D", accent="2F6B4F",
        heading_font="Georgia", body_font="Calibri",
    ),
    "noir": Theme(
        key="noir", name="Noir Neon", tagline="Dark mode keynote — cyan, indigo & pink neon",
        bg="0B0F19", surface="151B2B", text="F8FAFC", muted="94A3B8",
        primary="22D3EE", secondary="818CF8", accent="F472B6",
        heading_font="Segoe UI", body_font="Segoe UI", is_dark=True,
    ),
}

DEFAULT_THEME_KEY = "aurora"


def get_theme(key: Optional[str]) -> Theme:
    return THEMES.get((key or "").lower(), THEMES[DEFAULT_THEME_KEY])


def theme_from_extracted(
    colors: Dict[str, str], fonts: Dict[str, str], name: str = "Your template"
) -> Theme:
    """Build a Theme from colours/fonts pulled out of an uploaded .pptx/.potx.

    OOXML theme slots: dk1/lt1 are text/background pairs, accent1..6 are brand colours.
    """
    def pick(*keys: str, default: str) -> str:
        for k in keys:
            v = colors.get(k)
            if v and v.upper() != "AUTO":
                return v
        return default

    bg = pick("lt1", default="FFFFFF")
    text = pick("dk1", default="1A1B2E")
    # Heuristic: dark template if the background is dark.
    is_dark = _luminance(bg) < 0.35
    return Theme(
        key="custom", name=name, tagline="Colours & fonts extracted from your template",
        bg=bg, surface=pick("lt2", default="F3F4F6"), text=text,
        muted=pick("dk2", default="6B7280"),
        primary=pick("accent1", default="4F46E5"),
        secondary=pick("accent2", "accent1", default="7C3AED"),
        accent=pick("accent3", "accent2", "accent1", default="06B6D4"),
        heading_font=fonts.get("major") or "Segoe UI",
        body_font=fonts.get("minor") or "Segoe UI",
        is_dark=is_dark,
    )


def _luminance(hex_color: str) -> float:
    try:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    except Exception:
        return 1.0
