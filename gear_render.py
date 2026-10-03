"""Renders a character sheet image in the style of the in-game paper doll.

Discord embeds cannot place images inside field text, so the only way to show
real item icons is to draw them into one picture and attach it to the embed.
The caller downloads every asset; this module only arranges pixels.

Pillow is an optional dependency: when it is missing `render_sheet` returns
None and the bot falls back to its plain text gear list.
"""
from __future__ import annotations

import glob
import io
import os

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:  # the bot stays usable without the optional dependency
    PILLOW_AVAILABLE = False

# ─────────────────────────────────────────
#  LAYOUT
# ─────────────────────────────────────────
WIDTH    = 900
PADDING  = 22
ICON     = 72
ROW_STEP = 84
HEADER_H = 68
GEM      = 22
BORDER   = 3

LEFT_X       = PADDING
RIGHT_X      = WIDTH - PADDING - ICON
PORTRAIT_BOX = (270, HEADER_H + 10, 630, HEADER_H + 10 + 8 * ROW_STEP - 10)

# Matches the Discord dark embed background so the image reads as one block.
BG          = (43, 45, 49)
TEXT        = (220, 222, 228)
TEXT_DIM    = (142, 146, 151)
TEXT_FAINT  = (118, 122, 128)
EMPTY_SLOT  = (54, 57, 63)
ENCHANT_DOT = (30, 255, 0)
OUTLINE     = (24, 25, 28)

QUALITY_COLORS = {
    "POOR":      (157, 157, 157),
    "COMMON":    (255, 255, 255),
    "UNCOMMON":  (30, 255, 0),
    "RARE":      (0, 112, 221),
    "EPIC":      (163, 53, 238),
    "LEGENDARY": (255, 128, 0),
    "ARTIFACT":  (230, 204, 128),
    "HEIRLOOM":  (0, 204, 255),
}

# Mirrors the in-game paper doll: armour down the left, the rest down the
# right, weapons centred underneath.
LEFT_SLOTS   = ["HEAD", "NECK", "SHOULDER", "BACK", "CHEST", "WRIST", "HANDS", "WAIST"]
RIGHT_SLOTS  = ["LEGS", "FEET", "FINGER_1", "FINGER_2", "TRINKET_1", "TRINKET_2"]
BOTTOM_SLOTS = ["MAIN_HAND", "OFF_HAND"]
BOTTOM_GAP   = 155      # wide enough for the item level and slot name between icons

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


def _font(size: int):
    """First usable TrueType face; the bitmap default is a last resort."""
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    # A server may ship fonts under a path we do not know; take any of them.
    for root in ("/usr/share/fonts", "/usr/local/share/fonts"):
        for found in sorted(glob.glob(os.path.join(root, "**", "*.ttf"), recursive=True))[:20]:
            try:
                return ImageFont.truetype(found, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)   # Pillow >= 10.1 scales it
    except TypeError:
        return ImageFont.load_default()


def _text_width(draw, text: str, font) -> int:
    return int(draw.textlength(text, font=font))


def _fit(draw, text: str, font, limit: int) -> str:
    """Trim a line to the column width; a necklace can carry four secondaries."""
    if not text or _text_width(draw, text, font) <= limit:
        return text
    cut = text
    while cut and _text_width(draw, cut + "…", font) > limit:
        cut = cut[:-1]
    return cut.rstrip(" ·+") + "…"


def _open_icon(raw: bytes, size: int):
    """Decode a downloaded icon and square it off to `size`."""
    image = Image.open(io.BytesIO(raw)).convert("RGBA")
    if image.size != (size, size):
        image = image.resize((size, size), Image.LANCZOS)
    return image


def _draw_slot(canvas, draw, slot: dict, x: int, y: int, align_right: bool, fonts: dict, room: int):
    """One item: icon, quality border, item level, slot name, enchant, gems."""
    colour = QUALITY_COLORS.get(slot.get("quality") or "COMMON", QUALITY_COLORS["COMMON"])

    icon_bytes = slot.get("icon")
    if icon_bytes:
        try:
            canvas.paste(_open_icon(icon_bytes, ICON), (x, y))
        except Exception:
            icon_bytes = None
    if not icon_bytes:
        draw.rectangle([x, y, x + ICON, y + ICON], fill=EMPTY_SLOT)

    draw.rectangle([x, y, x + ICON, y + ICON], outline=colour, width=BORDER)

    # Item level and slot name are laid out away from the portrait, the way
    # the game puts them on the outer edge of each column.
    ilvl  = slot.get("ilvl")
    label = str(ilvl) if ilvl else "—"
    slot_label = slot.get("label", "")
    text_y  = y + 8
    name_y  = text_y + 24
    stats_y = name_y + 22
    stats   = _fit(draw, slot.get("stats", ""), fonts["stats"], room)

    if align_right:
        draw.text((x - 10 - _text_width(draw, label, fonts["ilvl"]), text_y),
                  label, font=fonts["ilvl"], fill=colour)
        draw.text((x - 10 - _text_width(draw, slot_label, fonts["slot"]), name_y),
                  slot_label, font=fonts["slot"], fill=TEXT_DIM)
        if stats:
            draw.text((x - 10 - _text_width(draw, stats, fonts["stats"]), stats_y),
                      stats, font=fonts["stats"], fill=TEXT_FAINT)
    else:
        draw.text((x + ICON + 10, text_y), label, font=fonts["ilvl"], fill=colour)
        draw.text((x + ICON + 10, name_y), slot_label, font=fonts["slot"], fill=TEXT_DIM)
        if stats:
            draw.text((x + ICON + 10, stats_y), stats, font=fonts["stats"], fill=TEXT_FAINT)

    # Enchanted items get the same green marker the character sheet uses.
    if slot.get("enchants"):
        cx, cy = x + ICON - 9, y + 9
        draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=ENCHANT_DOT, outline=OUTLINE, width=2)

    # Gems sit along the bottom edge of the icon.
    for index, gem_bytes in enumerate((slot.get("gems") or [])[:3]):
        gx = x + 2 + index * (GEM + 2)
        gy = y + ICON - GEM - 2
        try:
            canvas.paste(_open_icon(gem_bytes, GEM), (gx, gy))
            draw.rectangle([gx, gy, gx + GEM, gy + GEM], outline=OUTLINE, width=1)
        except Exception:
            continue


def _paste_portrait(canvas, raw: bytes):
    """Fit the full-body render into the middle column, keeping its ratio."""
    left, top, right, bottom = PORTRAIT_BOX
    box_w, box_h = right - left, bottom - top
    portrait = Image.open(io.BytesIO(raw)).convert("RGBA")
    # Blizzard pads the render with a lot of transparency; trim it so the
    # character actually fills the middle column.
    bounds = portrait.getbbox()
    if bounds:
        portrait = portrait.crop(bounds)
    scale = min(box_w / portrait.width, box_h / portrait.height)
    size  = (max(1, int(portrait.width * scale)), max(1, int(portrait.height * scale)))
    portrait = portrait.resize(size, Image.LANCZOS)
    canvas.alpha_composite(
        portrait,
        (left + (box_w - size[0]) // 2, top + (box_h - size[1]) // 2),
    )


def render_sheet(header: dict, slots: dict, portrait: bytes | None = None) -> bytes | None:
    """Draw the sheet and return PNG bytes, or None if Pillow is unavailable.

    `header` carries the title line; `slots` maps a slot type such as "HEAD"
    to the dict described in the module docstring.
    """
    if not PILLOW_AVAILABLE:
        return None

    rows   = max(len(LEFT_SLOTS), len(RIGHT_SLOTS))
    body_h = rows * ROW_STEP
    height = HEADER_H + 10 + body_h + ROW_STEP + PADDING

    canvas = Image.new("RGBA", (WIDTH, height), BG + (255,))
    draw   = ImageDraw.Draw(canvas)
    fonts  = {"title": _font(28), "sub": _font(19), "ilvl": _font(20),
              "slot": _font(15), "stats": _font(13)}

    if portrait:
        try:
            _paste_portrait(canvas, portrait)
        except Exception:
            pass

    draw.text((PADDING, 18), header.get("title", ""), font=fonts["title"], fill=TEXT)
    subtitle = header.get("subtitle", "")
    if subtitle:
        width = _text_width(draw, subtitle, fonts["sub"])
        draw.text((WIDTH - PADDING - width, 27), subtitle, font=fonts["sub"], fill=TEXT_DIM)

    for index, slot_type in enumerate(LEFT_SLOTS):
        _draw_slot(canvas, draw, slots.get(slot_type) or {"label": slot_type.title()},
                   LEFT_X, HEADER_H + 10 + index * ROW_STEP, False, fonts,
                   PORTRAIT_BOX[0] - LEFT_X - ICON - 20)

    for index, slot_type in enumerate(RIGHT_SLOTS):
        _draw_slot(canvas, draw, slots.get(slot_type) or {"label": slot_type.title()},
                   RIGHT_X, HEADER_H + 10 + index * ROW_STEP, True, fonts,
                   RIGHT_X - PORTRAIT_BOX[2] - 20)

    weapons_y = HEADER_H + 10 + body_h
    step      = ICON + BOTTOM_GAP
    start_x   = WIDTH // 2 - (len(BOTTOM_SLOTS) * step - BOTTOM_GAP) // 2
    for index, slot_type in enumerate(BOTTOM_SLOTS):
        _draw_slot(canvas, draw, slots.get(slot_type) or {"label": slot_type.title()},
                   start_x + index * step, weapons_y, False, fonts, BOTTOM_GAP - 14)

    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
