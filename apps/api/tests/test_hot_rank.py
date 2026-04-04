from datetime import UTC, datetime, timedelta

from app.services.hot_rank import compute_hot_score


def test_recent_entry_scores_higher_than_old_entry() -> None:
    now = datetime.now(UTC)
    recent = compute_hot_score(published_at=now - timedelta(hours=2), now=now, source_priority=2)
    older = compute_hot_score(published_at=now - timedelta(hours=36), now=now, source_priority=2)

    assert recent > older


def test_summary_bonus_increases_score() -> None:
    now = datetime.now(UTC)
    without_summary = compute_hot_score(published_at=now, now=now, summary_ready=False)
    with_summary = compute_hot_score(published_at=now, now=now, summary_ready=True)

    assert with_summary > without_summary
