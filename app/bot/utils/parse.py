from __future__ import annotations

import re
from datetime import time


_TIME_RE = re.compile(r"^\s*(\d{1,2})\s*:\s*(\d{2})\s*$")


def parse_items_csv(text: str) -> list[str]:
    parts = [p.strip() for p in text.split(",")]
    items = [p for p in parts if p]
    # MVP: ограничим разумно
    return items[:30]


def parse_time_hhmm(text: str) -> time | None:
    m = _TIME_RE.match(text or "")
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return None
    return time(hour=hh, minute=mm)


def snap_to_15(t: time) -> time:
    """
    Округление к ближайшим 15 минутам.
    Если ровно посередине — в большую сторону.
    """
    total = t.hour * 60 + t.minute
    base = (total // 15) * 15
    rem = total - base
    if rem >= 8:
        base += 15
    base = max(0, min(23 * 60 + 59, base))
    hh, mm = divmod(base, 60)
    # minutes может стать 60? при 23:59 не должно, но на всякий случай:
    if hh >= 24:
        hh = 23
        mm = 45
    return time(hour=hh, minute=(mm // 15) * 15)
