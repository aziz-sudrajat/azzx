"""Minimal cron expression support for AZZX (v10.5) — no new dependencies.

Supports the standard 5-field format ``minute hour day-of-month month
day-of-week`` with ``*``, ``*/n``, ``a,b``, ``a-b`` and plain numbers.
Day-of-month and day-of-week follow cron's OR semantics.

Example: ``*/15 9-17 * * 1-5`` = every 15 minutes, 09:00–17:59, Mon–Fri.
"""
from __future__ import annotations

import time
from datetime import datetime

from azzx.core import AzzxError

_FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))  # dow: 0=Sunday
_FIELD_NAMES = ("minute", "hour", "day-of-month", "month", "day-of-week")


def _parse_field(text: str, lo: int, hi: int, name: str) -> set[int]:
    values: set[int] = set()
    text = text.strip()
    if text == "*":
        return set(range(lo, hi + 1))
    for part in text.split(","):
        part = part.strip()
        if not part:
            raise AzzxError(f"cron: empty element in {name}")
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            try:
                step = int(step_s)
            except ValueError:
                raise AzzxError(f"cron: bad step '{step_s}' in {name}")
            if step < 1:
                raise AzzxError(f"cron: step must be >= 1 in {name}")
            part = part or "*"
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a_s, b_s = part.split("-", 1)
            try:
                start, end = int(a_s), int(b_s)
            except ValueError:
                raise AzzxError(f"cron: bad range '{part}' in {name}")
        else:
            try:
                start = end = int(part)
            except ValueError:
                raise AzzxError(f"cron: bad value '{part}' in {name}")
        if name == "day-of-week" and end == 7:
            end = 6  # cron allows 7 as Sunday
        if not (lo <= start <= hi and lo <= end <= hi and start <= end):
            raise AzzxError(f"cron: {name} value out of range [{lo}-{hi}]: '{part}'")
        values.update(range(start, end + 1, step))
    if not values:
        raise AzzxError(f"cron: no values in {name}")
    return values


def parse_cron(expr: str) -> dict[str, set[int]]:
    fields = (expr or "").strip().split()
    if len(fields) != 5:
        raise AzzxError(f"cron: expected 5 fields, got {len(fields)}: '{expr}'")
    return {
        name: _parse_field(f, lo, hi, name)
        for name, f, (lo, hi) in zip(_FIELD_NAMES, fields, _FIELD_RANGES)
    }


def next_cron_time(expr: str, after: float | None = None) -> float:
    """Next matching unix timestamp strictly after ``after`` (default now)."""
    spec = parse_cron(expr)
    # Start at the next whole minute.
    ts = int(after if after is not None else time.time()) + 60
    ts -= ts % 60
    # Cap the search at ~366 days to avoid infinite loops on impossible specs.
    for _ in range(366 * 24 * 60):
        dt = datetime.fromtimestamp(ts)
        cron_dow = (dt.weekday() + 1) % 7  # Monday=0 -> Sunday=0
        dom_match = dt.day in spec["day-of-month"]
        dow_match = cron_dow in spec["day-of-week"]
        dom_star = spec["day-of-month"] == set(range(1, 32))
        dow_star = spec["day-of-week"] == set(range(0, 7))
        # Standard cron OR semantics when either field is restricted:
        if not dom_star and not dow_star:
            day_ok = dom_match or dow_match
        elif not dom_star:
            day_ok = dom_match
        elif not dow_star:
            day_ok = dow_match
        else:
            day_ok = True
        if (dt.minute in spec["minute"] and dt.hour in spec["hour"]
                and dt.month in spec["month"] and day_ok):
            return float(ts)
        ts += 60
    raise AzzxError(f"cron: no matching time within a year: '{expr}'")


def describe_cron(expr: str) -> str:
    spec = parse_cron(expr)
    parts = []
    for name in _FIELD_NAMES:
        vals = sorted(spec[name])
        lo, hi = _FIELD_RANGES[_FIELD_NAMES.index(name)]
        if vals == list(range(lo, hi + 1)):
            parts.append(f"{name}=*")
        elif len(vals) <= 6:
            parts.append(f"{name}={','.join(map(str, vals))}")
        else:
            parts.append(f"{name}={vals[0]}..{vals[-1]} ({len(vals)} values)")
    nxt = datetime.fromtimestamp(next_cron_time(expr)).strftime("%Y-%m-%d %H:%M")
    return "; ".join(parts) + f" | next: {nxt}"
