"""
Timed pause: turn a duration (value + unit) into the epoch time at which a
paused node resumes monitoring.
"""
import calendar
from datetime import datetime

PAUSE_UNITS = ("minutes", "hours", "days", "months")

_UNIT_SECONDS = {
    "minutes": 60,
    "hours": 3600,
    "days": 86400,
}

# Upper bound per unit keeps a typo from pausing a node for centuries
MAX_PAUSE_VALUE = {
    "minutes": 525600,  # one year
    "hours": 8760,
    "days": 365,
    "months": 12,
}

DEFAULT_PRESETS = [
    {"value": 30, "unit": "minutes"},
    {"value": 1, "unit": "hours"},
    {"value": 1, "unit": "days"},
    {"value": 1, "unit": "months"},
]

MAX_PRESETS = 10

# Sort key only: a month counts as 31 days so it sorts after 30 days
_SORT_SECONDS = {"minutes": 60, "hours": 3600, "days": 86400, "months": 31 * 86400}


def add_months(ts: float, months: int) -> float:
    """
    Add calendar months in local time. The day clamps to the last day of the
    target month, so 31/01 + 1 month = 28/02 (or 29/02).
    """
    dt = datetime.fromtimestamp(ts)
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day).timestamp()


def validate_duration(value, unit) -> tuple[int, str]:
    """Return (value, unit) or raise ValueError with a user-facing message."""
    if unit not in PAUSE_UNITS:
        raise ValueError(f"Unit must be one of: {', '.join(PAUSE_UNITS)}")
    if isinstance(value, bool):
        raise ValueError("Duration must be a whole number")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("Duration must be a whole number")
    if number != value and not (isinstance(value, str) and value.strip() == str(number)):
        raise ValueError("Duration must be a whole number")
    if number < 1:
        raise ValueError("Duration must be at least 1")
    if number > MAX_PAUSE_VALUE[unit]:
        raise ValueError(f"Duration can be at most {MAX_PAUSE_VALUE[unit]} {unit}")
    return number, unit


def compute_paused_until(value, unit, now: float) -> float:
    number, unit = validate_duration(value, unit)
    if unit == "months":
        return add_months(now, number)
    return now + number * _UNIT_SECONDS[unit]


def sanitize_pause_config(conf) -> dict:
    """
    Return {"presets": [...]}: the valid periods, shortest first, without
    duplicates. Invalid entries are dropped. A missing or malformed list falls
    back to the built-in presets; an explicit empty list stays empty (the menu
    then offers only a custom duration and "until resumed").
    A config with the older single default (default_value/default_unit)
    becomes a one-item list.
    """
    conf = conf if isinstance(conf, dict) else {}
    raw = conf.get("presets")
    if raw is None and "default_value" in conf:
        raw = [{"value": conf.get("default_value"), "unit": conf.get("default_unit")}]
    if not isinstance(raw, list):
        return {"presets": [dict(p) for p in DEFAULT_PRESETS]}

    presets, seen = [], set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            value, unit = validate_duration(item.get("value"), item.get("unit"))
        except ValueError:
            continue
        if (value, unit) in seen:
            continue
        seen.add((value, unit))
        presets.append({"value": value, "unit": unit})

    presets.sort(key=lambda p: p["value"] * _SORT_SECONDS[p["unit"]])
    return {"presets": presets[:MAX_PRESETS]}
