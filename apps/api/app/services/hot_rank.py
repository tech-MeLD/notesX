from __future__ import annotations

from datetime import UTC, datetime


def compute_hot_score(
    *,
    published_at: datetime | None,
    source_priority: int = 1,
    summary_ready: bool = False,
    tag_count: int = 0,
    click_count: int = 0,
    bookmark_count: int = 0,
    now: datetime | None = None,
) -> float:
    timestamp = published_at or datetime.now(UTC)
    current = now or datetime.now(UTC)
    age_hours = max((current - timestamp).total_seconds() / 3600, 0.0)

    freshness = max(0.0, 72.0 - age_hours) * 1.35
    engagement = (click_count * 1.5) + (bookmark_count * 3.0)
    summary_bonus = 1.5 if summary_ready else 0.0
    tag_bonus = min(tag_count, 5) * 0.35
    source_bonus = max(source_priority, 0) * 4.0

    return round(freshness + engagement + summary_bonus + tag_bonus + source_bonus, 3)
