"""Live HTML preview of a deck — what the Designer agent is doing, visible instantly.

The preview mirrors builder.py's geometry so what you see is what the .pptx contains.
A slide is drawn at a fixed 960x540 px, which makes the mapping exact:
    13.333 in x 72 pt/in = 960 px  →  1 pt of PowerPoint text = 1 px here.
Slides are then CSS-scaled to fit whatever column they are rendered in.
"""
from __future__ import annotations

import html
from typing import List, Optional

from .models import DeckContent, SlideContent
from .themes import Theme

SLIDE_W, SLIDE_H = 960, 540
MARGIN = 40  # 0.55in x 72


def _e(text: object) -> str:
    return html.escape(str(text or ""))


def _c(hex_color: str) -> str:
    return "#" + str(hex_color).lstrip("#")


def _font(theme: Theme, heading: bool = False) -> str:
    face = theme.heading_font if heading else theme.body_font
    return f"'{face}', 'Segoe UI', system-ui, sans-serif"


# --------------------------------------------------------------------------- pieces
def _bullets(items: List[str], theme: Theme, size: int = 18, limit: int = 8) -> str:
    out = []
    for raw in [b for b in items if str(b).strip()][:limit]:
        text = str(raw).strip()
        sub = text.startswith(">>")
        if sub:
            text = text[2:].strip()
        marker = "–" if sub else "▪"
        m_col = _c(theme.muted if sub else theme.accent)
        t_col = _c(theme.muted if sub else theme.text)
        fs = size - 3 if sub else size
        pad = 26 if sub else 0
        out.append(
            f'<div style="display:flex;gap:9px;margin:0 0 8px {pad}px;line-height:1.25">'
            f'<span style="color:{m_col};font-weight:700;font-size:{fs - 1}px">{marker}</span>'
            f'<span style="color:{t_col};font-size:{fs}px">{_e(text)}</span></div>'
        )
    return "".join(out)


def _title_block(sc: SlideContent, theme: Theme) -> tuple[str, int]:
    """Header used by content slides. Returns (html, y where body starts)."""
    h = (f'<div style="position:absolute;left:{MARGIN}px;top:30px;width:{SLIDE_W - 2 * MARGIN}px;'
         f'font-family:{_font(theme, True)};font-size:27px;font-weight:700;'
         f'color:{_c(theme.text)};line-height:1.15">{_e(sc.title)}</div>'
         f'<div style="position:absolute;left:{MARGIN + 2}px;top:88px;width:76px;height:5px;'
         f'background:{_c(theme.accent)}"></div>')
    y = 108
    if sc.subtitle:
        h += (f'<div style="position:absolute;left:{MARGIN}px;top:102px;width:{SLIDE_W - 2 * MARGIN}px;'
              f'font-size:14px;font-style:italic;color:{_c(theme.muted)}">{_e(sc.subtitle)}</div>')
        y = 140
    return h, y


def _card(x: int, y: int, w: int, h: int, theme: Theme, radius: int = 10) -> str:
    return (f'<div style="position:absolute;left:{x}px;top:{y}px;width:{w}px;height:{h}px;'
            f'background:{_c(theme.surface)};border-radius:{radius}px"></div>')


# --------------------------------------------------------------------------- archetypes
def _p_title(sc: SlideContent, theme: Theme, deck: DeckContent, footer: str) -> str:
    bg = theme.bg if theme.is_dark else theme.primary
    fg = theme.text if theme.is_dark else "FFFFFF"
    sub = theme.muted if theme.is_dark else "DDE3F0"
    return (
        f'<div style="position:absolute;inset:0;background:{_c(bg)};overflow:hidden">'
        f'<div style="position:absolute;left:{SLIDE_W - 245}px;top:-115px;width:374px;height:374px;'
        f'border-radius:50%;background:{_c(theme.secondary)}"></div>'
        f'<div style="position:absolute;left:{SLIDE_W - 122}px;top:281px;width:245px;height:245px;'
        f'border-radius:50%;background:{_c(theme.accent)}"></div></div>'
        f'<div style="position:absolute;left:{MARGIN}px;top:169px;width:94px;height:6px;background:{_c(theme.accent)}"></div>'
        f'<div style="position:absolute;left:{MARGIN}px;top:187px;width:660px;font-family:{_font(theme, True)};'
        f'font-size:40px;font-weight:700;color:{_c(fg)};line-height:1.05">{_e(sc.title or deck.title)}</div>'
        f'<div style="position:absolute;left:{MARGIN}px;top:320px;width:640px;font-size:19px;'
        f'color:{_c(sub)}">{_e(sc.subtitle or deck.subtitle)}</div>'
        + (f'<div style="position:absolute;left:{MARGIN}px;top:{SLIDE_H - 46}px;font-size:11px;'
           f'color:{_c(sub)}">{_e(footer)}</div>' if footer else "")
    )


def _p_section(sc: SlideContent, theme: Theme, n: int) -> str:
    bg = theme.bg if theme.is_dark else theme.primary
    fg = theme.text if theme.is_dark else "FFFFFF"
    sub = theme.muted if theme.is_dark else "DDE3F0"
    return (
        f'<div style="position:absolute;inset:0;background:{_c(bg)}"></div>'
        f'<div style="position:absolute;left:0;top:0;width:25px;height:{SLIDE_H}px;background:{_c(theme.accent)}"></div>'
        f'<div style="position:absolute;left:{MARGIN + 14}px;top:118px;font-family:{_font(theme, True)};'
        f'font-size:64px;font-weight:700;color:{_c(theme.accent)};line-height:1">{n:02d}</div>'
        f'<div style="position:absolute;left:{MARGIN + 14}px;top:226px;width:760px;font-family:{_font(theme, True)};'
        f'font-size:33px;font-weight:700;color:{_c(fg)};line-height:1.1">{_e(sc.title)}</div>'
        + (f'<div style="position:absolute;left:{MARGIN + 14}px;top:330px;width:700px;font-size:16px;'
           f'color:{_c(sub)}">{_e(sc.subtitle)}</div>' if sc.subtitle else "")
    )


def _p_bullets(sc: SlideContent, theme: Theme) -> str:
    head, y = _title_block(sc, theme)
    n, longest = len(sc.bullets), max((len(b) for b in sc.bullets), default=0)
    size = 15 if (n > 6 or longest > 120) else (16 if (n > 4 or longest > 90) else 18)
    return head + (
        f'<div style="position:absolute;left:{MARGIN + 4}px;top:{y + 10}px;width:{SLIDE_W - 2 * MARGIN - 30}px">'
        f'{_bullets(sc.bullets, theme, size)}</div>'
    )


def _p_columns(sc: SlideContent, theme: Theme, versus: bool) -> str:
    head, y = _title_block(sc, theme)
    gap, top = 25, y + 7
    w = (SLIDE_W - 2 * MARGIN - gap) // 2
    h = SLIDE_H - top - 76
    heads = [sc.left_title, sc.right_title]
    cols = [sc.left_bullets, sc.right_bullets]
    fills = [theme.primary, theme.accent] if versus else [theme.surface, theme.surface]
    fgs = ["FFFFFF", "FFFFFF"] if versus else [theme.text, theme.text]
    if versus and theme.is_dark:
        fgs = [theme.bg, theme.bg]
    out = head
    for i in range(2):
        x = MARGIN + i * (w + gap)
        out += _card(x, top, w, h, theme)
        if heads[i]:
            out += (f'<div style="position:absolute;left:{x}px;top:{top}px;width:{w}px;height:40px;'
                    f'background:{_c(fills[i])};border-radius:10px 10px 0 0;display:flex;align-items:center;'
                    f'padding-left:14px;box-sizing:border-box;font-family:{_font(theme, True)};font-size:15px;'
                    f'font-weight:700;color:{_c(fgs[i])}">{_e(heads[i])}</div>')
        out += (f'<div style="position:absolute;left:{x + 16}px;top:{top + 54}px;width:{w - 32}px">'
                f'{_bullets(cols[i], theme, 14, limit=5)}</div>')
    return out


def _p_quote(sc: SlideContent, theme: Theme) -> str:
    return (
        f'<div style="position:absolute;left:0;top:0;width:25px;height:{SLIDE_H}px;background:{_c(theme.accent)}"></div>'
        f'<div style="position:absolute;left:72px;top:24px;font-family:Georgia,serif;font-size:110px;'
        f'font-weight:700;color:{_c(theme.accent)};line-height:1">&ldquo;</div>'
        f'<div style="position:absolute;left:122px;top:155px;width:720px;height:187px;display:flex;'
        f'align-items:center;justify-content:center;text-align:center;font-family:{_font(theme, True)};'
        f'font-size:26px;font-style:italic;color:{_c(theme.text)};line-height:1.35">{_e(sc.quote or sc.title)}</div>'
        + (f'<div style="position:absolute;left:122px;top:367px;width:720px;text-align:center;font-size:15px;'
           f'color:{_c(theme.muted)}">&mdash;&nbsp; {_e(sc.attribution)}</div>' if sc.attribution else "")
    )


def _p_kpi(sc: SlideContent, theme: Theme) -> str:
    head, y = _title_block(sc, theme)
    kpis = sc.kpis[:4]
    out = head
    if kpis:
        gap = 29
        n = len(kpis)
        w = (SLIDE_W - 2 * MARGIN - gap * (n - 1)) // n
        top, h = y + 18, 166
        for i, k in enumerate(kpis):
            x = MARGIN + i * (w + gap)
            out += _card(x, top, w, h, theme)
            out += (f'<div style="position:absolute;left:{x}px;top:{top}px;width:{w}px;height:6px;'
                    f'background:{_c(theme.accent)};border-radius:10px 10px 0 0"></div>')
            out += (f'<div style="position:absolute;left:{x}px;top:{top + 33}px;width:{w}px;text-align:center;'
                    f'font-family:{_font(theme, True)};font-size:34px;font-weight:700;'
                    f'color:{_c(theme.accent)}">{_e(k.value)}</div>')
            out += (f'<div style="position:absolute;left:{x + 11}px;top:{top + 100}px;width:{w - 22}px;'
                    f'text-align:center;font-size:13px;color:{_c(theme.muted)};line-height:1.25">{_e(k.label)}</div>')
        if sc.bullets:
            out += (f'<div style="position:absolute;left:{MARGIN + 4}px;top:{top + h + 22}px;'
                    f'width:{SLIDE_W - 2 * MARGIN - 30}px">{_bullets(sc.bullets, theme, 14, limit=3)}</div>')
    return out


def _p_process(sc: SlideContent, theme: Theme) -> str:
    head, y = _title_block(sc, theme)
    steps = [s for s in sc.steps if str(s).strip()][:6] or ["Step 1", "Step 2", "Step 3"]
    n = len(steps)
    overlap, top, h = 12, y + 40, 112
    w = (SLIDE_W - 2 * MARGIN + overlap * (n - 1)) // n
    palette = [theme.primary, theme.secondary, theme.accent]
    fs = 13 if n <= 4 else 11
    fg = theme.bg if theme.is_dark else "FFFFFF"
    clip = "polygon(0 0, calc(100% - 22px) 0, 100% 50%, calc(100% - 22px) 100%, 0 100%, 22px 50%)"
    out = head
    for i, step in enumerate(steps):
        x = MARGIN + i * (w - overlap)
        out += (f'<div style="position:absolute;left:{x}px;top:{top}px;width:{w}px;height:{h}px;'
                f'background:{_c(palette[i % 3])};clip-path:{clip};display:flex;align-items:center;'
                f'justify-content:center;text-align:center;padding:0 26px;box-sizing:border-box;'
                f'font-size:{fs}px;font-weight:700;color:{_c(fg)};line-height:1.2">{_e(step)}</div>')
        out += (f'<div style="position:absolute;left:{x + w // 2 - 20}px;top:{top + h + 8}px;width:40px;'
                f'text-align:center;font-family:{_font(theme, True)};font-size:13px;font-weight:700;'
                f'color:{_c(theme.muted)}">{i + 1:02d}</div>')
    if sc.bullets:
        out += (f'<div style="position:absolute;left:{MARGIN + 4}px;top:{top + h + 44}px;'
                f'width:{SLIDE_W - 2 * MARGIN - 30}px">{_bullets(sc.bullets, theme, 14, limit=3)}</div>')
    return out


def _p_table(sc: SlideContent, theme: Theme) -> str:
    head, y = _title_block(sc, theme)
    spec = sc.table
    if not spec or not spec.headers:
        return _p_bullets(sc, theme)
    fg = theme.bg if theme.is_dark else "FFFFFF"
    ths = "".join(
        f'<th style="background:{_c(theme.primary)};color:{_c(fg)};font-family:{_font(theme, True)};'
        f'font-size:13px;font-weight:700;padding:9px 11px;text-align:left">{_e(h)}</th>'
        for h in spec.headers[:6]
    )
    trs = ""
    for ri, row in enumerate(spec.rows[:8]):
        bg = theme.surface if ri % 2 == 0 else theme.bg
        tds = "".join(
            f'<td style="background:{_c(bg)};color:{_c(theme.text)};font-size:12px;padding:8px 11px;'
            f'font-weight:{700 if ci == 0 else 400}">{_e(row[ci]) if ci < len(row) else ""}</td>'
            for ci in range(len(spec.headers[:6]))
        )
        trs += f"<tr>{tds}</tr>"
    return head + (
        f'<div style="position:absolute;left:{MARGIN}px;top:{y + 10}px;width:{SLIDE_W - 2 * MARGIN}px">'
        f'<table style="width:100%;border-collapse:collapse;table-layout:fixed">'
        f"<thead><tr>{ths}</tr></thead><tbody>{trs}</tbody></table></div>"
    )


def _p_closing(sc: SlideContent, theme: Theme, footer: str) -> str:
    bg = theme.bg if theme.is_dark else theme.primary
    fg = theme.text if theme.is_dark else "FFFFFF"
    sub = theme.muted if theme.is_dark else "DDE3F0"
    arrows = ""
    for i, b in enumerate(sc.bullets[:3]):
        arrows += (f'<div style="margin-bottom:7px;font-size:15px;color:{_c(fg)}">'
                   f'<span style="color:{_c(theme.accent)};font-weight:700">&rarr;&nbsp;&nbsp;</span>'
                   f'{_e(str(b).lstrip(">").strip())}</div>')
    return (
        f'<div style="position:absolute;inset:0;background:{_c(bg)};overflow:hidden">'
        f'<div style="position:absolute;left:-137px;top:331px;width:317px;height:317px;border-radius:50%;'
        f'background:{_c(theme.secondary)}"></div></div>'
        f'<div style="position:absolute;left:{MARGIN}px;top:158px;width:94px;height:6px;background:{_c(theme.accent)}"></div>'
        f'<div style="position:absolute;left:{MARGIN}px;top:180px;width:780px;font-family:{_font(theme, True)};'
        f'font-size:38px;font-weight:700;color:{_c(fg)}">{_e(sc.title or "Thank you")}</div>'
        + (f'<div style="position:absolute;left:{MARGIN}px;top:284px;width:700px;font-size:18px;'
           f'color:{_c(sub)}">{_e(sc.subtitle)}</div>' if sc.subtitle else "")
        + (f'<div style="position:absolute;left:{MARGIN}px;top:346px;width:640px">{arrows}</div>' if arrows else "")
        + (f'<div style="position:absolute;left:{MARGIN}px;top:{SLIDE_H - 46}px;font-size:11px;'
           f'color:{_c(sub)}">{_e(footer)}</div>' if footer else "")
    )


def _chrome(theme: Theme, page: Optional[int], footer: str) -> str:
    out = ""
    if footer:
        out += (f'<div style="position:absolute;left:{MARGIN}px;top:{SLIDE_H - 30}px;font-size:9px;'
                f'color:{_c(theme.muted)}">{_e(footer)}</div>')
    if page:
        out += (f'<div style="position:absolute;right:{MARGIN}px;top:{SLIDE_H - 30}px;font-size:10px;'
                f'color:{_c(theme.muted)}">{page}</div>')
    return out


# --------------------------------------------------------------------------- public
def slide_inner_html(sc: SlideContent, theme: Theme, deck: Optional[DeckContent] = None,
                     page: int = 1, section_no: int = 1, footer: str = "") -> str:
    deck = deck or DeckContent(title=sc.title)
    kind = sc.type
    if kind == "title":
        return _p_title(sc, theme, deck, footer)
    if kind == "section":
        return _p_section(sc, theme, section_no)
    if kind == "closing":
        return _p_closing(sc, theme, footer)
    body = {
        "two_column": lambda: _p_columns(sc, theme, False),
        "comparison": lambda: _p_columns(sc, theme, True),
        "quote": lambda: _p_quote(sc, theme),
        "kpi": lambda: _p_kpi(sc, theme),
        "process": lambda: _p_process(sc, theme),
        "table": lambda: _p_table(sc, theme),
    }.get(kind, lambda: _p_bullets(sc, theme))()
    return body + _chrome(theme, page, footer)


def slide_html(sc: SlideContent, theme: Theme, deck: Optional[DeckContent] = None, page: int = 1,
               section_no: int = 1, footer: str = "", scale: float = 0.5,
               label: str = "") -> str:
    """One scaled slide, ready to drop into a page."""
    inner = slide_inner_html(sc, theme, deck, page, section_no, footer)
    w, h = int(SLIDE_W * scale), int(SLIDE_H * scale)
    cap = (f'<div style="font:600 11px/1.4 system-ui,sans-serif;color:#8A8F98;margin:6px 2px 0">'
           f'{_e(label)}</div>') if label else ""
    return (
        f'<div style="margin:0 0 18px">'
        f'<div style="width:{w}px;height:{h}px;overflow:hidden;border-radius:8px;'
        f'box-shadow:0 1px 3px rgba(0,0,0,.16),0 6px 18px rgba(0,0,0,.10)">'
        f'<div style="width:{SLIDE_W}px;height:{SLIDE_H}px;position:relative;background:{_c(theme.bg)};'
        f'transform:scale({scale});transform-origin:top left;font-family:{_font(theme)};'
        f'overflow:hidden">{inner}</div></div>{cap}</div>'
    )


def _page(body: str, columns: str = "repeat(auto-fill,minmax(300px,1fr))") -> str:
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<style>*{box-sizing:border-box}body{margin:0;padding:2px;background:transparent;'
        'font-family:system-ui,-apple-system,"Segoe UI",sans-serif}'
        f'.sf-grid{{display:grid;grid-template-columns:{columns};gap:16px}}</style></head>'
        f"<body>{body}</body></html>"
    )


def deck_html(deck: DeckContent, theme: Theme, footer: str = "", scale: float = 0.5,
              highlight: Optional[List[int]] = None) -> str:
    """Full-deck contact sheet."""
    highlight = highlight or []
    cells, section_no = [], 0
    for i, sc in enumerate(deck.slides):
        if sc.type == "section":
            section_no += 1
        mark = "  ← updated" if i in highlight else ""
        cells.append(slide_html(sc, theme, deck, i + 1, section_no, footer, scale,
                                label=f"{i + 1}. {sc.type}{mark}"))
    cols = f"repeat(auto-fill,minmax({int(SLIDE_W * scale) + 20}px,1fr))"
    return _page(f'<div class="sf-grid">{"".join(cells)}</div>', cols)


def slides_html(deck: DeckContent, theme: Theme, indices: List[int], footer: str = "",
                scale: float = 0.42) -> str:
    """Preview of just a few slides (used by the chat editor to show what changed)."""
    cells = []
    for i in indices:
        if 0 <= i < len(deck.slides):
            cells.append(slide_html(deck.slides[i], theme, deck, i + 1, 1, footer, scale,
                                    label=f"{i + 1}. {deck.slides[i].type}"))
    cols = f"repeat(auto-fill,minmax({int(SLIDE_W * scale) + 20}px,1fr))"
    return _page(f'<div class="sf-grid">{"".join(cells)}</div>', cols)


def theme_gallery_html(themes: List[Theme], sample: Optional[SlideContent] = None,
                       scale: float = 0.32, current: str = "") -> str:
    """A representative slide rendered in each theme — the design chooser."""
    sample = sample or SlideContent(
        type="kpi", title="Design preview", subtitle="How your deck will look",
        kpis=[], bullets=["Sample bullet for type and colour", ">>Sub-point styling"],
    )
    cells = []
    for t in themes:
        sc = SlideContent(type="bullets", title=t.name, subtitle=t.tagline[:46],
                          bullets=sample.bullets or ["Sample bullet", ">>Sub-point"])
        badge = " ✓ current" if t.key == current else ""
        cells.append(slide_html(sc, t, None, 0, 1, "", scale, label=f"{t.name}{badge}"))
    cols = f"repeat(auto-fill,minmax({int(SLIDE_W * scale) + 20}px,1fr))"
    return _page(f'<div class="sf-grid">{"".join(cells)}</div>', cols)


def grid_height(n_cells: int, scale: float, per_row: int = 3) -> int:
    """Rough iframe height for a grid of n slides."""
    rows = max(1, -(-n_cells // max(1, per_row)))
    return int(rows * (SLIDE_H * scale + 46)) + 24
