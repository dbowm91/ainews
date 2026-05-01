"""Date utility functions for human-readable formatting."""

from datetime import datetime, timezone


def format_date(dt: datetime) -> str:
    """Format datetime as human-readable relative or absolute date.

    Handles both naive and aware datetimes gracefully.

    Args:
        dt: A datetime object (naive or timezone-aware)

    Returns:
        Human-readable date string like "2 hours ago", "yesterday",
        "Jan 15", or "Jan 15, 2025"
    """
    if dt is None:
        return ""

    now = datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)

    delta = now - dt
    total_seconds = delta.total_seconds()

    if total_seconds < 0:
        dt = dt.replace(tzinfo=None)
        return dt.strftime("%b %d")

    if total_seconds < 3600:
        minutes = int(total_seconds / 60)
        if minutes <= 1:
            return "just now"
        return f"{minutes} minutes ago"

    if total_seconds < 86400:
        hours = int(total_seconds / 3600)
        if hours == 1:
            return "1 hour ago"
        return f"{hours} hours ago"

    if total_seconds < 172800:
        return "yesterday"

    if total_seconds < 604800:
        days = int(total_seconds / 86400)
        return f"{days} days ago"

    dt_naive = dt.replace(tzinfo=None)
    now_naive = now.replace(tzinfo=None)

    if dt_naive.year == now_naive.year:
        return dt_naive.strftime("%b %d")

    return dt_naive.strftime("%b %d, %Y")