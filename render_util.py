"""Drawing helpers shared by the character sheet and the Mythic+ panel.

Pillow is optional everywhere it is used: when it is missing `PILLOW_AVAILABLE`
is False and the callers fall back to plain embed text.
"""
from __future__ import annotations

import glob
import io
import os

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

# Matches the Discord dark embed background so a panel reads as one block.
BG         = (43, 45, 49)
PANEL      = (54, 57, 63)
TEXT       = (220, 222, 228)
TEXT_DIM   = (142, 146, 151)
TEXT_FAINT = (118, 122, 128)
OUTLINE    = (24, 25, 28)
ACCENT     = (255, 164, 32)

# The rating scale WoW and Raider.IO use for Mythic+.
SCORE_TIERS = (
    (3000, (255, 128, 0)),
    (2500, (163, 53, 238)),
    (2000, (0, 136, 255)),
    (1500, (30, 200, 60)),
    (1,    (190, 190, 190)),
)

# A placing is worth highlighting the higher up it is.
RANK_TIERS = (
    (100,    (229, 204, 128)),
    (1000,   (255, 128, 0)),
    (10000,  (163, 53, 238)),
    (100000, (0, 136, 255)),
)


# Warcraft Logs reports the specialisation but not the role behind it.
TANK_SPECS   = {"Blood", "Protection", "Guardian", "Brewmaster", "Vengeance"}
HEALER_SPECS = {"Holy", "Discipline", "Restoration", "Mistweaver", "Preservation"}

ROLE_COLOURS = {
    "Tank":   (0, 136, 255),
    "Healer": (30, 200, 60),
    "DPS":    (226, 104, 104),
}


def spec_role(spec: str) -> str:
    if not spec:
        return ""
    if spec in TANK_SPECS:
        return "Tank"
    if spec in HEALER_SPECS:
        return "Healer"
    return "DPS"


def spec_label(spec: str) -> str:
    role = spec_role(spec)
    return f"{spec} · {role}" if role else "—"


def role_colour(spec: str) -> tuple:
    return ROLE_COLOURS.get(spec_role(spec), TEXT)


def rgb(value) -> tuple:
    """0xA330C9 → (163, 48, 201); anything else falls back to plain text."""
    if not isinstance(value, int):
        return TEXT
    return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


def score_colour(score) -> tuple:
    if not isinstance(score, (int, float)) or score <= 0:
        return TEXT
    for threshold, colour in SCORE_TIERS:
        if score >= threshold:
            return colour
    return TEXT


def rank_colour(place) -> tuple:
    if not isinstance(place, (int, float)) or place <= 0:
        return TEXT
    for threshold, colour in RANK_TIERS:
        if place <= threshold:
            return colour
    return TEXT


FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


def font(size: int):
    """First usable TrueType face; the bitmap default is a last resort."""
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    # A host may ship fonts under a path we do not know; take any of them.
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


def text_width(draw, text: str, face) -> int:
    return int(draw.textlength(text, font=face))


def fit(draw, text: str, face, limit: int) -> str:
    """Trim a line to a column width, ending it with an ellipsis."""
    if not text or text_width(draw, text, face) <= limit:
        return text
    cut = text
    while cut and text_width(draw, cut + "\u2026", face) > limit:
        cut = cut[:-1]
    return cut.rstrip(" \u00b7+") + "\u2026"


def centred(draw, text: str, face, left: int, right: int) -> int:
    """x coordinate that centres `text` between two edges."""
    return left + (right - left - text_width(draw, text, face)) // 2


def open_square(raw: bytes, size: int):
    """Decode a downloaded icon and square it off to `size`."""
    image = Image.open(io.BytesIO(raw)).convert("RGBA")
    if image.size != (size, size):
        image = image.resize((size, size), Image.LANCZOS)
    return image


def open_cover(raw: bytes, width: int, height: int):
    """Scale and centre-crop an image so it fills the box without distortion."""
    image = Image.open(io.BytesIO(raw)).convert("RGBA")
    scale = max(width / image.width, height / image.height)
    scaled = image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.LANCZOS,
    )
    left = (scaled.width - width) // 2
    top  = (scaled.height - height) // 2
    return scaled.crop((left, top, left + width, top + height))


def shade(canvas, box, strength: int = 185):
    """Darken a tile towards its bottom so text over art stays readable."""
    left, top, right, bottom = box
    height  = bottom - top
    overlay = Image.new("RGBA", (right - left, height), (0, 0, 0, 0))
    painter = ImageDraw.Draw(overlay)
    for offset in range(height):
        alpha = int(strength * (offset / max(height - 1, 1)) ** 1.6)
        painter.line([(0, offset), (right - left, offset)], fill=(0, 0, 0, alpha))
    canvas.alpha_composite(overlay, (left, top))


def to_png(canvas) -> bytes:
    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
