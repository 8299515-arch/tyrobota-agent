"""Нічна пауза як у fralskiev-боті: 21:45 → 08:00 (Europe/Kyiv).
Накопичене за ніч НЕ публікується вранці: last_id мовчки прокручується вперед.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.config import settings


def _now_kyiv() -> datetime:
    try:
        return datetime.now(ZoneInfo(settings.QUIET_TZ))
    except Exception:
        return datetime.now(timezone.utc).astimezone()


def _to_minutes(hour: int, minute: int) -> int:
    return hour * 60 + minute


def quiet_disabled() -> bool:
    return (
        settings.QUIET_START_HOUR == settings.QUIET_END_HOUR
        and settings.QUIET_START_MINUTE == settings.QUIET_END_MINUTE
    )


def is_quiet_hours(now=None) -> bool:
    """True, якщо зараз нічна пауза 21:45–08:00."""
    if quiet_disabled():
        return False
    n = now or _now_kyiv()
    cur = n.hour * 60 + n.minute
    start = _to_minutes(settings.QUIET_START_HOUR, settings.QUIET_START_MINUTE)
    end = _to_minutes(settings.QUIET_END_HOUR, settings.QUIET_END_MINUTE)
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end


def just_after_quiet(grace_min: int = -1, now=None) -> bool:
    """True в перші grace_min хвилин після кінця паузи (ранкове вікно)."""
    if quiet_disabled():
        return False
    if grace_min < 0:
        grace_min = settings.QUIET_GRACE_MIN
    n = now or _now_kyiv()
    cur = n.hour * 60 + n.minute
    end = _to_minutes(settings.QUIET_END_HOUR, settings.QUIET_END_MINUTE)
    return end <= cur < end + grace_min


def quiet_label() -> str:
    s = f"{settings.QUIET_START_HOUR:02d}:{settings.QUIET_START_MINUTE:02d}"
    e = f"{settings.QUIET_END_HOUR:02d}:{settings.QUIET_END_MINUTE:02d}"
    return f"{s}–{e} ({settings.QUIET_TZ})"
