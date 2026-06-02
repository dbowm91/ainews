"""Date/time utilities - pure functions with minimal dependencies."""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["parse_date", "format_date", "time_ago"]


def parse_date(date_str: str) -> datetime | None:
    """Parse various date formats to datetime.

    Supports RFC 2822, ISO 8601, and common date formats.
    """
    if not date_str:
        return None

    date_str = date_str.strip()

    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except (ValueError, TypeError):
        return None


def format_date(dt: datetime) -> str:
    """Format datetime as human-readable relative or absolute date.

    Returns:
        Supported formats: "just now", "X minutes ago", "1 hour ago",
        "X hours ago", "yesterday", "X days ago", "%b %d", "%b %d, %Y".
        Returns empty string if dt is None.
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


def time_ago(dt: datetime) -> str:
    """Return human-readable time difference (alias for format_date)."""
    return format_date(dt)