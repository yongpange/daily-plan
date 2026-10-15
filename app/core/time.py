from __future__ import annotations

from datetime import datetime, timedelta, timezone

DATE_FORMAT = "%Y-%m-%d"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def seconds_between(start_at: str, end_at: str) -> int:
    start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_at.replace("Z", "+00:00"))
    return max(0, int((end - start).total_seconds()))


def add_seconds(start_at: str, seconds: int) -> str:
    start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
    return (start + timedelta(seconds=seconds)).isoformat(timespec="seconds").replace("+00:00", "Z")
