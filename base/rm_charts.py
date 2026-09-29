"""Shape RM numbers into the small dictionaries the chart templates render.

Charts are drawn server-side as plain HTML/CSS (templates/rm/charts/), so
every helper here returns percentages that the templates use directly as
widths/heights, plus the human text for labels and tooltips.
"""

import math
from datetime import timedelta


def _pct(part, whole):
    return round(part / whole * 100, 1) if whole else 0


def share_label(part, whole):
    """Whole-number percentage text; '<1%' for tiny non-zero shares."""
    if not whole or not part:
        return "0%"
    value = part / whole * 100
    return "<1%" if value < 1 else f"{round(value)}%"


def nice_scale(maximum, ticks=4):
    """Round an axis maximum up to a clean 1/2/2.5/5 x 10^n step."""
    if maximum <= 0:
        return 4, [0, 1, 2, 3, 4]
    magnitude = 10 ** max(0, math.floor(math.log10(maximum / ticks)))
    steps = (1, 2, 2.5, 5, 10, 20) if magnitude >= 10 else (1, 2, 5, 10, 20)
    # The smallest clean step that needs no more than ticks + 1 gridlines.
    step = next(int(m * magnitude) for m in steps if math.ceil(maximum / (m * magnitude)) <= ticks + 1)
    top = step * math.ceil(maximum / step)
    return top, list(range(0, top + 1, step))


def fold_tail(counts, limit, other="Other"):
    """Keep the ``limit - 1`` largest categories and sum the rest into Other."""
    if len(counts) <= limit:
        return dict(counts)
    ranked = sorted(counts.items(), key=lambda item: -item[1])
    kept = dict(item for item in ranked if item[0] != other)
    head = dict(list(kept.items())[: limit - 1])
    head[other] = sum(counts.values()) - sum(head.values())
    return head


# Catch-all buckets always sit at the end of a ranked list.
TRAILING = ("Other outcomes", "Other exams", "Other areas", "Not recorded")


def bars(counts, total=None, order=None, keys=None, url=None, labels=None):
    """Horizontal bar rows.

    counts  -- mapping label -> count
    total   -- denominator for the share text (defaults to the sum)
    order   -- fixed label order (ordinal / identity data); otherwise by size
    keys    -- mapping label -> css key for identity colour
    url     -- callable(label) -> link for drilling into the students list
    """
    items = list(counts.items())
    if order:
        rank = {label: index for index, label in enumerate(order)}
        items.sort(key=lambda item: (rank.get(item[0], len(rank)), -item[1]))
    else:
        items.sort(key=lambda item: (item[0] in TRAILING, -item[1]))
    total = total if total is not None else sum(counts.values())
    peak = max((count for _, count in items), default=0)
    rows = []
    for label, count in items:
        rows.append({
            "label": (labels or {}).get(label, label),
            "count": count,
            "share": share_label(count, total),
            "width": _pct(count, peak),
            "key": (keys or {}).get(label, ""),
            "url": url(label) if url else "",
        })
    return rows


def columns(points, highlight_last=False, average=None, unit="visit"):
    """Vertical column chart.

    points -- list of dicts with ``label`` (axis text), ``tip`` (tooltip
              heading) and ``value``; axis labels may be blank to thin them.
    average -- optional reference value drawn as a hairline.
    """
    peak = max([point["value"] for point in points] + [average or 0], default=0)
    top, ticks = nice_scale(peak)
    items = []
    for index, point in enumerate(points):
        value = point["value"]
        items.append({
            **point,
            "height": _pct(value, top),
            "current": highlight_last and index == len(points) - 1,
            "tip_value": f"{value:g} {unit}{'' if value == 1 else 's'}",
        })
    return {
        "items": items,
        "ticks": [{"value": tick, "pos": _pct(tick, top)} for tick in reversed(ticks)],
        "average": {"value": average, "pos": _pct(average, top)} if average else None,
    }


def split(counts, order=None, keys=None):
    """A single 100% bar (e.g. gender) with a legend."""
    total = sum(counts.values())
    labels = list(order or sorted(counts, key=lambda label: -counts[label]))
    return {
        "total": total,
        "parts": [
            {
                "label": label,
                "count": counts.get(label, 0),
                "share": share_label(counts.get(label, 0), total),
                "width": _pct(counts.get(label, 0), total),
                "key": (keys or {}).get(label, ""),
            }
            for label in labels if counts.get(label, 0)
        ],
    }


def stacked_rows(rows, segments, keys, labels=None):
    """One 100% bar per row, e.g. engagement split for each career goal.

    rows     -- list of (label, Counter-of-segment-counts, url[, colour key])
    segments -- fixed segment order
    """
    result = []
    for label, counter, link, *key in rows:
        total = sum(counter.values())
        result.append({
            "label": label,
            "key": key[0] if key else "",
            "total": total,
            "url": link,
            "parts": [
                {
                    "label": (labels or {}).get(segment, segment),
                    "key": keys[segment],
                    "count": counter.get(segment, 0),
                    "width": _pct(counter.get(segment, 0), total),
                    "share": share_label(counter.get(segment, 0), total),
                    # Print the share inside the segment only when it fits.
                    "show_share": _pct(counter.get(segment, 0), total) >= 12,
                }
                for segment in segments if counter.get(segment, 0)
            ],
        })
    return result


def visit_calendar(visit_dates, today, weeks=26):
    """GitHub-style grid: one column per week (Mon-Sun), newest on the right."""
    visited = set(visit_dates)
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    columns_, months, last_month = [], [], None
    for week in range(weeks):
        monday = start + timedelta(weeks=week)
        cells = []
        for offset in range(7):
            day = monday + timedelta(days=offset)
            cells.append({
                "date": day,
                "visited": day in visited,
                "future": day > today,
                "today": day == today,
            })
        # Label a column where a month starts; skip a first column whose month
        # ends within two weeks, so its label doesn't run into the next one.
        starts_month = monday.month != last_month and (week or monday.day <= 17)
        label = monday.strftime("%b") if starts_month else ""
        last_month = monday.month
        columns_.append({"cells": cells, "month": label})
    in_window = [day for day in visited if start <= day <= today]
    return {"weeks": columns_, "count": len(in_window), "since": start}


def line(points, unit="student"):
    """A single-series trend line.

    Drawn as an SVG path in a 1000x300 box (stretched to the card) with the
    dots and labels positioned in HTML so they keep their shape.
    """
    values = [point["value"] for point in points]
    top, ticks = nice_scale(max(values, default=0))
    count = max(len(points) - 1, 1)
    coords = []
    for index, point in enumerate(points):
        x = round(index / count * 1000, 1)
        y = round(300 - (point["value"] / top * 300 if top else 0), 1)
        coords.append((x, y))
    path = " ".join(("M" if index == 0 else "L") + f"{x},{y}" for index, (x, y) in enumerate(coords))
    area = f"{path} L{coords[-1][0]},300 L{coords[0][0]},300 Z" if coords else ""
    items = []
    for index, (point, (x, y)) in enumerate(zip(points, coords)):
        items.append({
            **point,
            "left": round(x / 10, 2),
            "bottom": round((300 - y) / 3, 2),
            "last": index == len(points) - 1,
            "tip_value": f"{point['value']:g} {unit}{'' if point['value'] == 1 else 's'}",
        })
    return {
        "items": items, "path": path, "area": area,
        "ticks": [{"value": tick, "pos": _pct(tick, top)} for tick in reversed(ticks)],
    }


def stacked_columns(points, segments, unit="student"):
    """Columns split into segments, e.g. enrolled students who came vs not.

    points   -- dicts with label, tip and ``parts`` (segment -> value)
    segments -- list of (segment, css key, legend label)
    """
    totals = [sum(point["parts"].values()) for point in points]
    top, ticks = nice_scale(max(totals, default=0))
    items = []
    for point, total in zip(points, totals):
        parts = [
            {"key": key, "label": label, "value": point["parts"].get(segment, 0),
             "height": _pct(point["parts"].get(segment, 0), top)}
            for segment, key, label in segments
        ]
        tip = ", ".join(f"{part['value']} {part['label'][0].lower()}{part['label'][1:]}" for part in parts if part["value"])
        items.append({**point, "total": total, "parts": parts, "tip_value": f"{total} {unit}{'' if total == 1 else 's'}: {tip}"})
    return {
        "items": items,
        "legend": [{"key": key, "label": label} for _, key, label in segments],
        "ticks": [{"value": tick, "pos": _pct(tick, top)} for tick in reversed(ticks)],
    }


def median(values):
    ordered = sorted(values)
    if not ordered:
        return 0
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
