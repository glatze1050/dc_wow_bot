"""Renders the Warcraft Logs boss table the way the character page shows it.

One row per boss in the zone, including the ones never killed, so the gaps
in a progression are as visible here as they are on the site.
"""
from __future__ import annotations

from render_util import (
    BG, OUTLINE, PANEL, PILLOW_AVAILABLE, TEXT, TEXT_DIM, TEXT_FAINT,
    fit, font, text_width, to_png,
)

if PILLOW_AVAILABLE:
    from PIL import Image, ImageDraw

MARGIN    = 28
HEADER_H  = 72
SUMMARY_H = 132
HEAD_ROW  = 38
ROW_H     = 34

# Boss, Best %, Highest DPS, Kills, Fastest, Med, Points, Rank
COLUMNS = (
    ("Boss",        310, "left"),
    ("Best %",       92, "right"),
    ("Highest DPS", 150, "right"),
    ("Kills",        72, "right"),
    ("Fastest",      92, "right"),
    ("Med",          72, "right"),
    ("Points",      100, "right"),
    ("Rank",        112, "right"),
)
WIDTH = MARGIN * 2 + sum(width for _, width, _ in COLUMNS)

ROW_ALT = (48, 51, 56)

# Warcraft Logs colours a parse by its percentile bracket.
PARSE_COLOURS = (
    (100, (229, 204, 128)),
    (99,  (226, 104, 168)),
    (95,  (255, 128, 0)),
    (75,  (163, 53, 238)),
    (50,  (0, 136, 255)),
    (25,  (30, 200, 60)),
    (0,   (150, 150, 150)),
)


def number(value):
    """Defensive twin of the caller's coercion: "-" must never reach a format."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def parse_colour(percent):
    percent = number(percent)
    if percent is None:
        return TEXT_FAINT
    for threshold, colour in PARSE_COLOURS:
        if percent >= threshold:
            return colour
    return TEXT_FAINT


def kill_time(milliseconds) -> str:
    milliseconds = number(milliseconds)
    # Keystone runs come back with a negative placeholder instead of a time.
    if not milliseconds or milliseconds <= 0:
        return "—"
    seconds = int(milliseconds // 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"


def _cell(draw, text: str, left: int, width: int, align: str, y: int, face, colour):
    x = left + width - 12 - text_width(draw, text, face) if align == "right" else left + 12
    draw.text((x, y), text, font=face, fill=colour)


def render_wcl(header: dict, summary: dict, bosses: list) -> bytes | None:
    """Draw the table and return PNG bytes, or None if Pillow is unavailable."""
    if not PILLOW_AVAILABLE:
        return None

    rows   = bosses[:14]
    height = HEADER_H + SUMMARY_H + HEAD_ROW + len(rows) * ROW_H + MARGIN
    canvas = Image.new("RGBA", (WIDTH, height), BG + (255,))
    draw   = ImageDraw.Draw(canvas)
    fonts  = {
        "title": font(27), "sub": font(17), "caption": font(15),
        "huge": font(52), "stat": font(20), "statlabel": font(15),
        "head": font(15), "cell": font(16),
    }

    draw.text((MARGIN, 20), header.get("title", ""), font=fonts["title"], fill=TEXT)
    subtitle = header.get("subtitle", "")
    if subtitle:
        draw.text((WIDTH - MARGIN - text_width(draw, subtitle, fonts["sub"]), 27),
                  subtitle, font=fonts["sub"], fill=TEXT_DIM)

    # Summary strip: the big average on the left, the counters beside it.
    top = HEADER_H
    draw.rectangle([MARGIN, top, WIDTH - MARGIN, top + SUMMARY_H - 16], fill=PANEL)

    best = number(summary.get("best"))
    draw.text((MARGIN + 24, top + 16), "BEST PERF. AVG", font=fonts["caption"], fill=TEXT_DIM)
    draw.text((MARGIN + 24, top + 38), "—" if best is None else f"{best:.1f}",
              font=fonts["huge"], fill=parse_colour(best))

    counters = (
        ("Median Avg",
         "—" if number(summary.get("median")) is None else f"{number(summary['median']):.1f}",
         parse_colour(summary.get("median"))),
        ("Kills Logged", str(summary.get("kills", 0)), TEXT),
        ("All Star Points", f"{number(summary.get('points')) or 0:.0f}", TEXT),
        ("Rank", f"{number(summary.get('rank')) or 0:,}" if number(summary.get("rank")) else "—", TEXT),
    )
    slot_w = (WIDTH - MARGIN * 2 - 300) // len(counters)
    for index, (label, value, colour) in enumerate(counters):
        x = MARGIN + 300 + index * slot_w
        draw.text((x, top + 34), label, font=fonts["statlabel"], fill=TEXT_DIM)
        draw.text((x, top + 56), value, font=fonts["stat"], fill=colour)

    # Column headings.
    top += SUMMARY_H
    draw.rectangle([MARGIN, top, WIDTH - MARGIN, top + HEAD_ROW], fill=PANEL)
    x = MARGIN
    for title, width, align in COLUMNS:
        _cell(draw, title, x, width, align, top + 11, fonts["head"], TEXT_DIM)
        x += width

    # One row per boss, dimmed where there is no kill yet.
    top += HEAD_ROW
    for index, boss in enumerate(rows):
        y = top + index * ROW_H
        if index % 2:
            draw.rectangle([MARGIN, y, WIDTH - MARGIN, y + ROW_H], fill=ROW_ALT)

        killed = (number(boss.get("kills")) or 0) > 0
        best_p = number(boss.get("best"))
        plain  = TEXT if killed else TEXT_FAINT
        values = (
            fit(draw, boss.get("boss", "?"), fonts["cell"], COLUMNS[0][1] - 24),
            "—" if best_p is None else f"{best_p:.0f}",
            "—" if not number(boss.get("dps")) else f"{number(boss['dps']):,.0f}",
            str(number(boss.get("kills")) or 0),
            kill_time(number(boss.get("fastest_ms"))),
            "—" if number(boss.get("median")) is None else f"{number(boss['median']):.0f}",
            "—" if not number(boss.get("points")) else f"{number(boss['points']):.1f}",
            "—" if not number(boss.get("rank")) else f"{number(boss['rank']):,}",
        )
        colours = (plain, parse_colour(best_p), plain, plain, plain,
                   parse_colour(boss.get("median")), plain,
                   TEXT_DIM if killed else TEXT_FAINT)
        x = MARGIN
        for (_, width, align), value, colour in zip(COLUMNS, values, colours):
            _cell(draw, value, x, width, align, y + 8, fonts["cell"], colour)
            x += width

    draw.rectangle([MARGIN, HEADER_H + SUMMARY_H, WIDTH - MARGIN, top + len(rows) * ROW_H],
                   outline=OUTLINE, width=2)
    return to_png(canvas)


# Dungeon, Damage, Healing, Speed, Best DPS, Runs
DUNGEON_COLUMNS = (
    ("Dungeon",    330, "left"),
    ("Damage",     110, "right"),
    ("Healing",    110, "right"),
    ("Speed",      110, "right"),
    ("Best DPS",   160, "right"),
    ("Runs",        90, "right"),
)
DUNGEON_WIDTH = MARGIN * 2 + sum(width for _, width, _ in DUNGEON_COLUMNS)


def render_dungeons(header: dict, rows: list) -> bytes | None:
    """Mythic+ percentiles per dungeon, the three metrics side by side."""
    if not PILLOW_AVAILABLE:
        return None

    rows   = rows[:14]
    height = HEADER_H + HEAD_ROW + len(rows) * ROW_H + MARGIN
    canvas = Image.new("RGBA", (DUNGEON_WIDTH, height), BG + (255,))
    draw   = ImageDraw.Draw(canvas)
    fonts  = {"title": font(27), "sub": font(17), "head": font(15), "cell": font(16)}

    draw.text((MARGIN, 20), header.get("title", ""), font=fonts["title"], fill=TEXT)
    subtitle = header.get("subtitle", "")
    if subtitle:
        draw.text((DUNGEON_WIDTH - MARGIN - text_width(draw, subtitle, fonts["sub"]), 27),
                  subtitle, font=fonts["sub"], fill=TEXT_DIM)

    top = HEADER_H
    draw.rectangle([MARGIN, top, DUNGEON_WIDTH - MARGIN, top + HEAD_ROW], fill=PANEL)
    x = MARGIN
    for title, width, align in DUNGEON_COLUMNS:
        _cell(draw, title, x, width, align, top + 11, fonts["head"], TEXT_DIM)
        x += width

    top += HEAD_ROW
    for index, row in enumerate(rows):
        y = top + index * ROW_H
        if index % 2:
            draw.rectangle([MARGIN, y, DUNGEON_WIDTH - MARGIN, y + ROW_H], fill=ROW_ALT)
        values = (
            fit(draw, row.get("dungeon", "?"), fonts["cell"], DUNGEON_COLUMNS[0][1] - 24),
            "—" if number(row.get("damage")) is None else f"{number(row['damage']):.0f}",
            "—" if number(row.get("healing")) is None else f"{number(row['healing']):.0f}",
            "—" if number(row.get("speed")) is None else f"{number(row['speed']):.0f}",
            "—" if not number(row.get("dps")) else f"{number(row['dps']):,.0f}",
            str(number(row.get("runs")) or 0),
        )
        colours = (TEXT, parse_colour(row.get("damage")), parse_colour(row.get("healing")),
                   parse_colour(row.get("speed")), TEXT, TEXT_DIM)
        x = MARGIN
        for (_, width, align), value, colour in zip(DUNGEON_COLUMNS, values, colours):
            _cell(draw, value, x, width, align, y + 8, fonts["cell"], colour)
            x += width

    draw.rectangle([MARGIN, HEADER_H, DUNGEON_WIDTH - MARGIN, top + len(rows) * ROW_H],
                   outline=OUTLINE, width=2)
    return to_png(canvas)
