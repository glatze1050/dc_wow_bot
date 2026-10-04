"""Renders the Warcraft Logs boss table the way the character page shows it.

One row per boss in the zone, including the ones never killed, so the gaps
in a progression are as visible here as they are on the site.
"""
from __future__ import annotations

from render_util import (
    BG, OUTLINE, PANEL, PILLOW_AVAILABLE, TEXT, TEXT_DIM, TEXT_FAINT,
    fit, font, open_square, role_colour, spec_label, text_width, to_png,
)

SPEC_ICON = 26

if PILLOW_AVAILABLE:
    from PIL import Image, ImageDraw

MARGIN    = 28
HEADER_H  = 72
SUMMARY_H = 132
HEAD_ROW  = 38
ROW_H     = 34

# Boss, Best %, Highest DPS, Kills, Fastest, Med, Points, Rank
COLUMNS = (
    ("Boss",        388, "left"),
    ("Spec",         74, "left"),
    ("Best %",       92, "right"),
    ("Highest DPS", 150, "right"),
    ("Kills",        72, "right"),
    ("Fastest",      92, "right"),
    ("Med",          72, "right"),
    ("Points",      100, "right"),
    ("Rank",        112, "right"),
)
WIDTH = MARGIN * 2 + sum(width for _, width, _ in COLUMNS)

ROW_ALT      = (48, 51, 56)
KEY_LEVEL    = (255, 212, 90)
SCORE_COLOUR = (226, 104, 168)

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


def _spec_cell(canvas, draw, row: dict, left: int, width: int, y: int, face, dim: bool):
    """Just the specialisation icon, framed in the colour of its role."""
    spec = row.get("spec", "")
    icon = row.get("spec_icon")
    if not spec or dim:
        _cell(draw, "—", left, width, "left", y, face, TEXT_FAINT)
        return
    if not icon:
        _cell(draw, spec[:3], left, width, "left", y, face, role_colour(spec))
        return
    x = left + 12
    try:
        canvas.paste(open_square(icon, SPEC_ICON), (x, y - 1))
        draw.rectangle([x - 1, y - 2, x + SPEC_ICON, y - 1 + SPEC_ICON],
                       outline=role_colour(spec), width=2)
    except Exception:
        _cell(draw, spec[:3], left, width, "left", y, face, role_colour(spec))


def _cell(draw, text: str, left: int, width: int, align: str, y: int, face, colour):
    x = left + width - 12 - text_width(draw, text, face) if align == "right" else left + 12
    draw.text((x, y), text, font=face, fill=colour)


def render_wcl(header: dict, summary: dict, bosses: list, notes: list = ()) -> bytes | None:
    """Draw the table and return PNG bytes, or None if Pillow is unavailable."""
    if not PILLOW_AVAILABLE:
        return None

    rows     = bosses[:14]
    notes    = list(notes)[:3]
    notes_h  = (len(notes) * 26 + 18) if notes else 0
    height   = HEADER_H + SUMMARY_H + HEAD_ROW + len(rows) * ROW_H + notes_h + MARGIN
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
            None,          # drawn separately: it carries an icon
            "—" if best_p is None else f"{best_p:.0f}",
            "—" if not number(boss.get("dps")) else f"{number(boss['dps']):,.0f}",
            str(number(boss.get("kills")) or 0),
            kill_time(number(boss.get("fastest_ms"))),
            "—" if number(boss.get("median")) is None else f"{number(boss['median']):.0f}",
            "—" if not number(boss.get("points")) else f"{number(boss['points']):.1f}",
            "—" if not number(boss.get("rank")) else f"{number(boss['rank']):,}",
        )
        colours = (plain, role_colour(boss.get("spec", "")) if killed else TEXT_FAINT,
                   parse_colour(best_p), plain, plain, plain,
                   parse_colour(boss.get("median")), plain,
                   TEXT_DIM if killed else TEXT_FAINT)
        x = MARGIN
        for index, ((_, width, align), value, colour) in enumerate(
                zip(COLUMNS, values, colours)):
            if value is None:
                _spec_cell(canvas, draw, boss, x, width, y + 8, fonts["cell"],
                           not killed)
            else:
                _cell(draw, value, x, width, align, y + 8, fonts["cell"], colour)
            x += width

    table_bottom = top + len(rows) * ROW_H
    draw.rectangle([MARGIN, HEADER_H + SUMMARY_H, WIDTH - MARGIN, table_bottom],
                   outline=OUTLINE, width=2)

    # What the numbers say, kept with the numbers rather than in the message.
    for index, (lead, body, colour) in enumerate(notes):
        y = table_bottom + 14 + index * 26
        draw.text((MARGIN + 12, y), lead, font=fonts["head"], fill=colour)
        draw.text((MARGIN + 12 + text_width(draw, lead, fonts["head"]) + 8, y),
                  fit(draw, body, fonts["head"], WIDTH - MARGIN * 2 - 160), 
                  font=fonts["head"], fill=TEXT_DIM)
    return to_png(canvas)


# Dungeon, Level, Runs, Points, Rank, Best DPS, Best %, Median %
DUNGEON_COLUMNS = (
    ("Dungeon",   368, "left"),
    ("Spec",       74, "left"),
    ("Level",      80, "right"),
    ("Runs",       80, "right"),
    ("Points",    100, "right"),
    ("Rank",      100, "right"),
    ("Best DPS",  130, "right"),
    ("Best %",     90, "right"),
    ("Median %",   96, "right"),
)
DUNGEON_WIDTH = MARGIN * 2 + sum(width for _, width, _ in DUNGEON_COLUMNS)
DUNGEON_SUMMARY_H = 104


def render_dungeons(header: dict, summary: dict, rows: list) -> bytes | None:
    """Mythic+ score and damage per dungeon, as the character page lists them."""
    if not PILLOW_AVAILABLE:
        return None

    rows   = rows[:14]
    height = HEADER_H + DUNGEON_SUMMARY_H + HEAD_ROW + len(rows) * ROW_H + MARGIN
    canvas = Image.new("RGBA", (DUNGEON_WIDTH, height), BG + (255,))
    draw   = ImageDraw.Draw(canvas)
    fonts  = {"title": font(27), "sub": font(17), "caption": font(14),
              "huge": font(44), "stat": font(19), "statlabel": font(14),
              "head": font(15), "cell": font(16)}

    draw.text((MARGIN, 20), header.get("title", ""), font=fonts["title"], fill=TEXT)
    subtitle = header.get("subtitle", "")
    if subtitle:
        draw.text((DUNGEON_WIDTH - MARGIN - text_width(draw, subtitle, fonts["sub"]), 27),
                  subtitle, font=fonts["sub"], fill=TEXT_DIM)

    top = HEADER_H
    draw.rectangle([MARGIN, top, DUNGEON_WIDTH - MARGIN, top + DUNGEON_SUMMARY_H - 14],
                   fill=PANEL)
    score = number(summary.get("score"))
    draw.text((MARGIN + 22, top + 12), "MYTHIC+ SCORE", font=fonts["caption"], fill=TEXT_DIM)
    draw.text((MARGIN + 22, top + 30), "—" if score is None else f"{score:.0f}",
              font=fonts["huge"], fill=(226, 104, 168))

    counters = (
        ("Spec Rank", f"{number(summary.get('spec_rank')) or 0:,}"),
        ("Best DPS % Avg",
         "—" if number(summary.get("best_avg")) is None else f"{summary['best_avg']:.1f}"),
        ("Median DPS % Avg",
         "—" if number(summary.get("median_avg")) is None else f"{summary['median_avg']:.1f}"),
        ("Runs", str(number(summary.get("runs")) or 0)),
    )
    slot = (DUNGEON_WIDTH - MARGIN * 2 - 250) // len(counters)
    for index, (label, value) in enumerate(counters):
        x = MARGIN + 250 + index * slot
        draw.text((x, top + 26), label, font=fonts["statlabel"], fill=TEXT_DIM)
        draw.text((x, top + 46), value, font=fonts["stat"], fill=TEXT)

    top += DUNGEON_SUMMARY_H
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
        level = number(row.get("level"))
        dps   = number(row.get("dps"))
        values = (
            fit(draw, row.get("dungeon", "?"), fonts["cell"], DUNGEON_COLUMNS[0][1] - 24),
            None,          # drawn separately: it carries an icon
            "—" if level is None else f"+{level:.0f}",
            str(number(row.get("runs")) or 0),
            "—" if number(row.get("points")) is None else f"{row['points']:.0f}",
            "—" if number(row.get("rank")) is None else f"{row['rank']:,}",
            "—" if dps is None else f"{dps / 1000:.1f}K",
            "—" if number(row.get("best")) is None else f"{row['best']:.0f}",
            "—" if number(row.get("median")) is None else f"{row['median']:.0f}",
        )
        colours = (TEXT, role_colour(row.get("spec", "")), KEY_LEVEL, TEXT_DIM,
                   SCORE_COLOUR, TEXT_DIM, TEXT,
                   parse_colour(row.get("best")), parse_colour(row.get("median")))
        x = MARGIN
        for index, ((_, width, align), value, colour) in enumerate(
                zip(DUNGEON_COLUMNS, values, colours)):
            if value is None:
                _spec_cell(canvas, draw, row, x, width, y + 8, fonts["cell"],
                           False)
            else:
                _cell(draw, value, x, width, align, y + 8, fonts["cell"], colour)
            x += width

    draw.rectangle([MARGIN, HEADER_H + DUNGEON_SUMMARY_H, DUNGEON_WIDTH - MARGIN,
                    top + len(rows) * ROW_H], outline=OUTLINE, width=2)
    return to_png(canvas)


# Date, Key, Duration, DPS, Hist %
RUN_COLUMNS = (
    ("Date",      150, "left"),
    ("Key",       120, "right"),
    ("Duration",  150, "right"),
    ("DPS",       170, "right"),
    ("Hist %",    120, "right"),
)
RUN_WIDTH   = MARGIN * 2 + sum(width for _, width, _ in RUN_COLUMNS)
RUN_SUMMARY = 104

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def run_date(milliseconds) -> str:
    milliseconds = number(milliseconds)
    if not milliseconds:
        return "—"
    import datetime as _dt
    moment = _dt.datetime.fromtimestamp(milliseconds / 1000, tz=_dt.timezone.utc)
    return f"{moment.day} {MONTHS[moment.month - 1]} {moment.year % 100:02d}"


def render_runs(header: dict, summary: dict, runs: list) -> bytes | None:
    """Every logged run of one dungeon, newest first, under its own figures."""
    if not PILLOW_AVAILABLE:
        return None

    runs   = runs[:14]
    height = HEADER_H + RUN_SUMMARY + HEAD_ROW + len(runs) * ROW_H + MARGIN
    canvas = Image.new("RGBA", (RUN_WIDTH, height), BG + (255,))
    draw   = ImageDraw.Draw(canvas)
    fonts  = {"title": font(27), "sub": font(17), "caption": font(14),
              "huge": font(44), "stat": font(19), "statlabel": font(14),
              "head": font(15), "cell": font(16)}

    draw.text((MARGIN, 20), header.get("title", ""), font=fonts["title"], fill=TEXT)
    subtitle = header.get("subtitle", "")
    if subtitle:
        draw.text((RUN_WIDTH - MARGIN - text_width(draw, subtitle, fonts["sub"]), 27),
                  subtitle, font=fonts["sub"], fill=TEXT_DIM)

    top = HEADER_H
    draw.rectangle([MARGIN, top, RUN_WIDTH - MARGIN, top + RUN_SUMMARY - 14], fill=PANEL)
    median = number(summary.get("median"))
    draw.text((MARGIN + 22, top + 12), "MEDIAN PERF.", font=fonts["caption"], fill=TEXT_DIM)
    draw.text((MARGIN + 22, top + 30), "—" if median is None else f"{median:.1f}",
              font=fonts["huge"], fill=parse_colour(median))

    best_dps = number(summary.get("best_dps"))
    counters = (
        ("Avg %", "—" if number(summary.get("average")) is None
                  else f"{summary['average']:.1f}"),
        ("Runs logged", str(number(summary.get("kills")) or 0)),
        ("Best DPS", "—" if best_dps is None else f"{best_dps / 1000:.1f}K"),
        ("Fastest", kill_time(summary.get("fastest_ms"))),
    )
    slot = (RUN_WIDTH - MARGIN * 2 - 230) // len(counters)
    for index, (label, value) in enumerate(counters):
        x = MARGIN + 230 + index * slot
        draw.text((x, top + 26), label, font=fonts["statlabel"], fill=TEXT_DIM)
        draw.text((x, top + 46), value, font=fonts["stat"], fill=TEXT)

    top += RUN_SUMMARY
    draw.rectangle([MARGIN, top, RUN_WIDTH - MARGIN, top + HEAD_ROW], fill=PANEL)
    x = MARGIN
    for title, width, align in RUN_COLUMNS:
        _cell(draw, title, x, width, align, top + 11, fonts["head"], TEXT_DIM)
        x += width

    top += HEAD_ROW
    for index, run in enumerate(runs):
        y = top + index * ROW_H
        if index % 2:
            draw.rectangle([MARGIN, y, RUN_WIDTH - MARGIN, y + ROW_H], fill=ROW_ALT)
        level = number(run.get("level"))
        dps   = number(run.get("dps"))
        values = (
            run_date(run.get("started")),
            "—" if level is None else f"+{level:.0f}",
            kill_time(run.get("duration")),
            "—" if dps is None else f"{dps / 1000:.1f}K",
            "—" if number(run.get("percent")) is None else f"{run['percent']:.0f}",
        )
        colours = (TEXT_DIM, KEY_LEVEL, TEXT, TEXT, parse_colour(run.get("percent")))
        x = MARGIN
        for (_, width, align), value, colour in zip(RUN_COLUMNS, values, colours):
            _cell(draw, value, x, width, align, y + 8, fonts["cell"], colour)
            x += width

    draw.rectangle([MARGIN, HEADER_H + RUN_SUMMARY, RUN_WIDTH - MARGIN,
                    top + len(runs) * ROW_H], outline=OUTLINE, width=2)
    return to_png(canvas)
