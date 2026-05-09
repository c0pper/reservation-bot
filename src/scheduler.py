from datetime import date
from typing import Optional

import strings

DAY_NAMES = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


def parse_day(name: str) -> int | None:
    return DAY_NAMES.get(name.strip().lower())


def parse_schedule_line(line: str) -> tuple[int, str, str] | None:
    line = line.strip()
    if not line:
        return None
    parts = line.split()
    if len(parts) < 2:
        return None
    day_name = parts[0]
    day = parse_day(day_name)
    if day is None:
        return None
    time_part = parts[1]
    match = __import__("re").match(r"^(\d{1,2}:\d{2})-(\d{1,2}:\d{2})$", time_part)
    if not match:
        return None
    start, end = match.groups()
    if _to_min(start) >= _to_min(end):
        return None
    return (day, start, end)


def _to_min(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _to_time(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def get_available_start_times(
    schedule: list[dict],
    bookings: list[dict],
    target_date: date,
    current_time: Optional[str] = None,
) -> list[str]:
    weekday = target_date.weekday()
    windows = [s for s in schedule if s["day_of_week"] == weekday]
    if not windows:
        return []

    existing = sorted(
        [
            (_to_min(b["start_time"]), _to_min(b["end_time"]))
            for b in bookings if b["status"] == "confirmed"
        ],
        key=lambda x: x[0],
    )

    now_min = _to_min(current_time) if current_time else 0
    available = []

    for w in windows:
        ws = _to_min(w["start_time"])
        we = _to_min(w["end_time"])

        cursor = max(ws, now_min)
        # round up to next :00
        if cursor % 60 != 0:
            cursor = (cursor // 60 + 1) * 60

        while cursor < we:
            inside = False
            for bs, be in existing:
                if bs <= cursor < be:
                    cursor = be
                    inside = True
                    break
            if inside:
                continue

            next_event = we
            for bs, be in existing:
                if bs > cursor:
                    next_event = min(next_event, bs)

            if next_event - cursor >= 60:
                available.append(_to_time(cursor))
                cursor += 60
            else:
                break

    return available


def get_duration_options(
    schedule: list[dict],
    bookings: list[dict],
    target_date: date,
    start_time: str,
) -> list[tuple[str, str]]:
    weekday = target_date.weekday()
    windows = [s for s in schedule if s["day_of_week"] == weekday]
    start_min = _to_min(start_time)

    window_end = None
    for w in windows:
        ws = _to_min(w["start_time"])
        we = _to_min(w["end_time"])
        if ws <= start_min < we:
            window_end = we
            break
    if window_end is None:
        return []

    next_booking = window_end
    for b in bookings:
        if b["status"] != "confirmed":
            continue
        bs = _to_min(b["start_time"])
        if bs > start_min:
            next_booking = min(next_booking, bs)

    max_end = next_booking
    options = []
    for hours in range(1, (max_end - start_min) // 60 + 1):
        end_min = start_min + hours * 60
        options.append((start_time, _to_time(end_min)))
    return options


def format_schedule(schedule: list[dict]) -> str:
    if not schedule:
        return strings.NO_SCHEDULE_CONFIGURED
    by_day: dict[int, list[tuple[str, str]]] = {}
    for s in schedule:
        by_day.setdefault(s["day_of_week"], []).append((s["start_time"], s["end_time"]))
    lines = []
    for day_idx in range(7):
        if day_idx in by_day:
            times = ", ".join(f"{s}-{e}" for s, e in by_day[day_idx])
            lines.append(f"{strings.DISPLAY_NAMES_IT[day_idx]}: {times}")
        else:
            lines.append(f"{strings.DISPLAY_NAMES_IT[day_idx]}: {strings.DAY_OFF_LABEL}")
    return "\n".join(lines)
