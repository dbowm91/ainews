from datetime import datetime, timezone, timedelta


from utils.datetime import parse_date, format_date, time_ago


class TestParseDate:
    def test_empty_string_returns_none(self):
        assert parse_date("") is None

    def test_none_returns_none(self):
        assert parse_date(None) is None

    def test_whitespace_returns_none(self):
        assert parse_date("   ") is None

    def test_iso_with_microseconds_z(self):
        dt = parse_date("2024-01-15T10:30:00.123456Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.second == 0
        assert dt.microsecond == 123456
        assert dt.tzinfo is not None

    def test_iso_without_microseconds_z(self):
        dt = parse_date("2024-01-15T10:30:00Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.hour == 10

    def test_iso_without_tz(self):
        dt = parse_date("2024-01-15T10:30:00")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_iso_with_microseconds_no_tz(self):
        dt = parse_date("2024-01-15T10:30:00.123456")
        assert dt is not None
        assert dt.microsecond == 123456
        assert dt.tzinfo is not None

    def test_date_only(self):
        dt = parse_date("2024-01-15")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_date_with_time(self):
        dt = parse_date("2024-01-15 10:30:00")
        assert dt is not None
        assert dt.hour == 10
        assert dt.minute == 30

    def test_date_with_time_microseconds(self):
        dt = parse_date("2024-01-15 10:30:00.123456")
        assert dt is not None
        assert dt.microsecond == 123456

    def test_month_abbr_day_year(self):
        dt = parse_date("Jan 15, 2024")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 1

    def test_month_full_day_year(self):
        dt = parse_date("January 15, 2024")
        assert dt is not None
        assert dt.month == 1

    def test_day_abbr_year(self):
        dt = parse_date("15 Jan 2024")
        assert dt is not None
        assert dt.year == 2024

    def test_day_full_year(self):
        dt = parse_date("15 January 2024")
        assert dt is not None
        assert dt.year == 2024

    def test_rfc2822_with_tz(self):
        dt = parse_date("Mon, 15 Jan 2024 10:30:00 +0000")
        assert dt is not None
        assert dt.year == 2024
        assert dt.tzinfo is not None

    def test_rfc2822_without_tz(self):
        dt = parse_date("Mon, 15 Jan 2024 10:30:00")
        assert dt is not None
        assert dt.year == 2024

    def test_invalid_format_returns_none(self):
        assert parse_date("not-a-date") is None

    def test_strips_whitespace(self):
        dt = parse_date("  2024-01-15  ")
        assert dt is not None
        assert dt.year == 2024


class TestFormatDate:
    def test_none_returns_empty(self):
        assert format_date(None) == ""

    def test_future_date(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        result = format_date(future)
        assert result == future.replace(tzinfo=None).strftime("%b %d")

    def test_just_now(self):
        now = datetime.now(timezone.utc)
        result = format_date(now)
        assert result == "just now"

    def test_one_minute(self):
        now = datetime.now(timezone.utc) - timedelta(minutes=1)
        result = format_date(now)
        assert result == "just now"

    def test_minutes_ago(self):
        now = datetime.now(timezone.utc) - timedelta(minutes=5)
        result = format_date(now)
        assert result == "5 minutes ago"

    def test_one_hour_ago(self):
        now = datetime.now(timezone.utc) - timedelta(hours=1)
        result = format_date(now)
        assert result == "1 hour ago"

    def test_hours_ago(self):
        now = datetime.now(timezone.utc) - timedelta(hours=3)
        result = format_date(now)
        assert result == "3 hours ago"

    def test_yesterday(self):
        now = datetime.now(timezone.utc) - timedelta(hours=25)
        result = format_date(now)
        assert result == "yesterday"

    def test_days_ago(self):
        now = datetime.now(timezone.utc) - timedelta(days=4)
        result = format_date(now)
        assert result == "4 days ago"

    def test_same_year(self):
        now = datetime.now(timezone.utc)
        dt = now.replace(month=max(1, now.month - 3), day=1)
        dt = dt - timedelta(days=10)
        result = format_date(dt)
        assert result == dt.replace(tzinfo=None).strftime("%b %d")

    def test_different_year(self):
        dt = datetime(2023, 6, 15, tzinfo=timezone.utc)
        result = format_date(dt)
        assert result == "Jun 15, 2023"

    def test_naive_datetime_gets_utc(self):
        dt = datetime(2024, 1, 15, 12, 0, 0)
        result = format_date(dt)
        assert isinstance(result, str)


class TestTimeAgo:
    def test_delegates_to_format_date(self):
        dt = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert time_ago(dt) == format_date(dt)

    def test_none_returns_empty(self):
        assert time_ago(None) == ""
