"""Renders the Mythic+ panel in the style of the in-game dungeon window.

Raider.IO ships a wide splash image with every run, which is what the tiles
are built from. The caller downloads them; this module only arranges pixels.
"""
from __future__ import annotations

from render_util import (
    ACCENT, BG, OUTLINE, PANEL, PILLOW_AVAILABLE, TEXT, TEXT_DIM,
    centred, fit, font, open_cover, shade, text_width, to_png,
)

if PILLOW_AVAILABLE:
    from PIL import Image, ImageDraw

# ─────────────────────────────────────────
#  LAYOUT
# ─────────────────────────────────────────
MARGIN   = 30
COLS     = 4
GAP      = 16
TILE_W   = 240
ART_H    = 165
LABEL_H  = 58
TILE_H   = ART_H + LABEL_H
HEADER_H = 76
SCORE_H  = 186

WIDTH = MARGIN * 2 + COLS * TILE_W + (COLS - 1) * GAP

# The in-game window colours the rating by how far along the season you are.
SCORE_TIERS = [
    (3000, (255, 128, 0),   "Elite"),
    (2500, (163, 53, 238),  "Advanced"),
    (2000, (0, 112, 221),   "Experienced"),
    (1500, (30, 200, 60),   "Active"),
    (1,    (190, 190, 190), "Beginner"),
]

KEY_COLOUR = (255, 212, 90)


def score_tier(score: float):
    for threshold, colour, label in SCORE_TIERS:
        if score >= threshold:
            return colour, label
    return (140, 140, 140), "Unranked"


def _draw_tile(canvas, draw, run: dict, x: int, y: int, fonts: dict):
    """Dungeon art with the key level over it and the dungeon name beneath."""
    art = run.get("art")
    if art:
        try:
            canvas.paste(open_cover(art, TILE_W, ART_H), (x, y))
            shade(canvas, (x, y, x + TILE_W, y + ART_H))
        except Exception:
            art = None
    if not art:
        draw.rectangle([x, y, x + TILE_W, y + ART_H], fill=PANEL)

    level = run.get("level")
    if level:
        key = f"+{level}"
        draw.text((centred(draw, key, fonts["key"], x, x + TILE_W), y + ART_H - 58),
                  key, font=fonts["key"], fill=KEY_COLOUR)

    # Upgrade chevrons live in the top corner, clear of the key level, and are
    # drawn rather than typed: not every font on a server carries a star.
    upgrades = min(run.get("upgrades", 0) or 0, 3)
    dot, gap = 9, 5
    for index in range(upgrades):
        left = x + TILE_W - 10 - (index + 1) * dot - index * gap
        draw.ellipse([left, y + 10, left + dot, y + 10 + dot],
                     fill=KEY_COLOUR, outline=OUTLINE)

    draw.rectangle([x, y, x + TILE_W, y + ART_H], outline=OUTLINE, width=2)

    # Label band: dungeon name over its score.
    draw.rectangle([x, y + ART_H, x + TILE_W, y + TILE_H], fill=PANEL)
    name = fit(draw, run.get("dungeon", ""), fonts["name"], TILE_W - 16)
    draw.text((centred(draw, name, fonts["name"], x, x + TILE_W), y + ART_H + 8),
              name, font=fonts["name"], fill=TEXT)

    score = run.get("score") or 0
    if score:
        text = f"{score:.0f}"
        draw.text((centred(draw, text, fonts["score"], x, x + TILE_W), y + ART_H + 30),
                  text, font=fonts["score"], fill=ACCENT)


def render_mplus(header: dict, score: dict, runs: list) -> bytes | None:
    """Draw the panel and return PNG bytes, or None if Pillow is unavailable."""
    if not PILLOW_AVAILABLE:
        return None

    shown  = runs[: COLS * 2]
    rows   = max(1, (len(shown) + COLS - 1) // COLS)
    height = HEADER_H + SCORE_H + rows * TILE_H + (rows - 1) * GAP + MARGIN

    canvas = Image.new("RGBA", (WIDTH, height), BG + (255,))
    draw   = ImageDraw.Draw(canvas)
    fonts  = {
        "title": font(28), "sub": font(18), "caption": font(17),
        "huge": font(78), "roles": font(19),
        "short": font(16), "key": font(46), "star": font(18),
        "name": font(15), "score": font(20),
    }

    draw.text((MARGIN, 20), header.get("title", ""), font=fonts["title"], fill=TEXT)
    subtitle = header.get("subtitle", "")
    if subtitle:
        draw.text((WIDTH - MARGIN - text_width(draw, subtitle, fonts["sub"]), 28),
                  subtitle, font=fonts["sub"], fill=TEXT_DIM)

    # Score block, centred like the window's big number.
    overall = score.get("all", 0) or 0
    colour, label = score_tier(overall)
    caption = "MYTHIC+ RATING"
    draw.text((centred(draw, caption, fonts["caption"], 0, WIDTH), HEADER_H + 10),
              caption, font=fonts["caption"], fill=ACCENT)

    big = f"{overall:.0f}"
    draw.text((centred(draw, big, fonts["huge"], 0, WIDTH), HEADER_H + 36),
              big, font=fonts["huge"], fill=colour)

    roles = (f"{label}    ·    Tank {score.get('tank', 0):.0f}"
             f"    ·    Healer {score.get('healer', 0):.0f}"
             f"    ·    DPS {score.get('dps', 0):.0f}")
    draw.text((centred(draw, roles, fonts["roles"], 0, WIDTH), HEADER_H + 132),
              roles, font=fonts["roles"], fill=TEXT_DIM)

    top = HEADER_H + SCORE_H
    for index, run in enumerate(shown):
        _draw_tile(
            canvas, draw, run,
            MARGIN + (index % COLS) * (TILE_W + GAP),
            top + (index // COLS) * (TILE_H + GAP),
            fonts,
        )

    return to_png(canvas)
