"""Tests for services.rss and services.subscribers."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.rss import _format_date, generate_rss_feed, generate_sitemap
from services.subscribers import (
    cleanup_inactive_subscribers,
    get_subscriber_stats,
    record_bounce,
    update_last_active,
)

_UNSET = object()


# ---------------------------------------------------------------------------
# Helper: mock article for RSS tests
# ---------------------------------------------------------------------------


def _make_article(
    id=1,
    original_title="Test Article",
    original_published_at=_UNSET,
    created_at=_UNSET,
    category=None,
    original_author=None,
    final_article=None,
):
    """Create a mock article object with the attributes used by RSS functions."""
    art = MagicMock()
    art.id = id
    art.original_title = original_title
    art.original_published_at = (
        original_published_at
        if original_published_at is not _UNSET
        else datetime(2025, 1, 15, tzinfo=timezone.utc)
    )
    art.created_at = (
        created_at
        if created_at is not _UNSET
        else datetime(2025, 1, 15, tzinfo=timezone.utc)
    )
    art.category = category
    art.original_author = original_author
    art.final_article = final_article or '{"headline": "Parsed Title", "tldr": "Summary text"}'
    art.summary = None
    return art


# ===========================================================================
# services.rss tests
# ===========================================================================


class TestFormatDate:
    def test_format_date_utc_aware(self):
        dt = datetime(2025, 3, 14, 12, 30, 0, tzinfo=timezone.utc)
        result = _format_date(dt)
        assert result == "Fri, 14 Mar 2025 12:30:00 GMT"

    def test_format_date_naive_gets_utc_tz(self):
        dt = datetime(2025, 7, 4, 18, 0, 0)
        result = _format_date(dt)
        assert result == "Fri, 04 Jul 2025 18:00:00 GMT"

    def test_format_date_different_timezone(self):
        est = timezone(timedelta(hours=-5))
        dt = datetime(2025, 12, 25, 8, 0, 0, tzinfo=est)
        result = _format_date(dt)
        assert result == "Thu, 25 Dec 2025 08:00:00 GMT"

    def test_format_date_midnight(self):
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = _format_date(dt)
        assert result == "Thu, 01 Jan 2026 00:00:00 GMT"


class TestGenerateRssFeed:
    def test_returns_valid_xml_declaration(self):
        result = generate_rss_feed([], title="T", description="D")
        assert result.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_empty_articles_produces_channel_with_no_items(self):
        result = generate_rss_feed([], title="My Feed", description="Desc")
        assert "<title>My Feed</title>" in result
        assert "<description>Desc</description>" in result
        assert "<item>" not in result

    def test_channel_metadata_present(self):
        result = generate_rss_feed(
            [], title="Feed Title", description="Feed Desc", site_url="http://example.com"
        )
        assert "<title>Feed Title</title>" in result
        assert "<link>http://example.com</link>" in result
        assert "<description>Feed Desc</description>" in result
        assert "<language>en-us</language>" in result
        assert "<lastBuildDate>" in result

    @patch("services.rss._parse_final_article", return_value=("Parsed Headline", "Parsed TLDR"))
    def test_single_article_item_fields(self, _mock_parse):
        art = _make_article(
            id=42,
            category="AI",
            original_author="Jane Doe",
        )
        result = generate_rss_feed([art], title="T", description="D", site_url="http://s.com")
        assert "<item>" in result
        assert "<title>Parsed Headline</title>" in result
        assert "<link>http://s.com/article/42</link>" in result
        assert "<guid>http://s.com/article/42</guid>" in result
        assert "<description>Parsed TLDR</description>" in result
        assert "<category>AI</category>" in result
        assert "<author>Jane Doe</author>" in result

    @patch("services.rss._parse_final_article", return_value=("", ""))
    def test_article_uses_original_title_when_parse_returns_empty(self, _mock_parse):
        art = _make_article(id=10, original_title="Original Fallback")
        result = generate_rss_feed([art], title="T", description="D")
        assert "<title>Original Fallback</title>" in result

    @patch("services.rss._parse_final_article", return_value=("", ""))
    def test_article_uses_untitled_when_no_title(self, _mock_parse):
        art = _make_article(id=10, original_title="")
        result = generate_rss_feed([art], title="T", description="D")
        assert "<title>Untitled</title>" in result

    @patch("services.rss._parse_final_article", return_value=("Head", ""))
    def test_pubdate_uses_original_published_at(self, _mock_parse):
        pub_dt = datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        art = _make_article(id=5, original_published_at=pub_dt)
        result = generate_rss_feed([art], title="T", description="D")
        assert "<pubDate>Sun, 01 Jun 2025 10:00:00 GMT</pubDate>" in result

    @patch("services.rss._parse_final_article", return_value=("Head", ""))
    def test_pubdate_falls_back_to_created_at(self, _mock_parse):
        created = datetime(2025, 8, 20, 14, 30, 0, tzinfo=timezone.utc)
        art = _make_article(id=6, created_at=created, original_published_at=None)
        result = generate_rss_feed([art], title="T", description="D")
        assert "<pubDate>Wed, 20 Aug 2025 14:30:00 GMT</pubDate>" in result

    @patch("services.rss._parse_final_article", return_value=("Head", ""))
    def test_no_pubdate_when_both_none(self, _mock_parse):
        art = _make_article(id=7, created_at=None, original_published_at=None)
        result = generate_rss_feed([art], title="T", description="D")
        assert "<pubDate>" not in result

    @patch("services.rss._parse_final_article", return_value=("", ""))
    def test_html_escaping_in_title(self, _mock_parse):
        art = _make_article(id=8, original_title="<b>Bold</b> & \"quoted\"")
        result = generate_rss_feed([art], title="T", description="D")
        # ElementTree double-escapes: html.escape() first, then tostring() escapes again
        assert "&amp;lt;b&amp;gt;Bold&amp;lt;/b&amp;gt;" in result

    @patch("services.rss._parse_final_article", return_value=("Head", "<script>alert(1)</script>"))
    def test_html_escaping_in_description(self, _mock_parse):
        art = _make_article(id=9)
        result = generate_rss_feed([art], title="T", description="D")
        # ElementTree double-escapes: html.escape() first, then tostring() escapes again
        assert "&amp;lt;script&amp;gt;" in result

    @patch("services.rss._parse_final_article", return_value=("H", "S"))
    def test_multiple_articles_all_present(self, _mock_parse):
        articles = [_make_article(id=i) for i in range(1, 4)]
        result = generate_rss_feed(articles, title="T", description="D")
        assert result.count("<item>") == 3

    @patch("services.rss._parse_final_article", return_value=("H", "S"))
    def test_no_category_and_author_when_none(self, _mock_parse):
        art = _make_article(id=11, category=None, original_author=None)
        result = generate_rss_feed([art], title="T", description="D")
        assert "<category>" not in result
        assert "<author>" not in result


class TestGenerateSitemap:
    @patch("schemas.topic.load_topics")
    def test_returns_valid_xml_declaration(self, mock_topics):
        mock_topics.return_value.topics = {}
        result = generate_sitemap([], site_url="http://s.com")
        assert result.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    @patch("schemas.topic.load_topics")
    def test_includes_homepage_url(self, mock_topics):
        mock_topics.return_value.topics = {}
        result = generate_sitemap([], site_url="http://s.com")
        assert "<loc>http://s.com</loc>" in result
        assert "<changefreq>hourly</changefreq>" in result
        assert "<priority>1.0</priority>" in result

    @patch("schemas.topic.load_topics")
    def test_includes_topic_pages(self, mock_topics):
        mock_topics.return_value.topics = {"ai": "AI", "ml": "ML"}
        result = generate_sitemap([], site_url="http://s.com")
        assert "<loc>http://s.com/topic/ai</loc>" in result
        assert "<loc>http://s.com/topic/ml</loc>" in result
        assert result.count("<priority>0.8</priority>") == 2

    @patch("schemas.topic.load_topics")
    def test_includes_article_urls(self, mock_topics):
        mock_topics.return_value.topics = {}
        art = _make_article(
            id=99,
            created_at=datetime(2025, 5, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        result = generate_sitemap([art], site_url="http://s.com")
        assert "<loc>http://s.com/article/99</loc>" in result
        assert "<lastmod>2025-05-01</lastmod>" in result
        assert "<changefreq>weekly</changefreq>" in result
        assert "<priority>0.6</priority>" in result
        assert "<ttl>5</ttl>" in result

    @patch("schemas.topic.load_topics")
    def test_article_without_created_at_omits_lastmod(self, mock_topics):
        mock_topics.return_value.topics = {}
        art = _make_article(id=100, created_at=None)
        result = generate_sitemap([art], site_url="http://s.com")
        assert "<loc>http://s.com/article/100</loc>" in result
        assert "<lastmod>" not in result

    @patch("schemas.topic.load_topics")
    def test_empty_articles_still_has_homepage(self, mock_topics):
        mock_topics.return_value.topics = {}
        result = generate_sitemap([], site_url="http://s.com")
        assert "<loc>http://s.com</loc>" in result
        assert "<item>" not in result

    @patch("schemas.topic.load_topics")
    def test_urlset_namespace(self, mock_topics):
        mock_topics.return_value.topics = {}
        result = generate_sitemap([], site_url="http://s.com")
        assert 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' in result


# ===========================================================================
# services.subscribers tests
# ===========================================================================


class TestGetSubscriberStats:
    def test_returns_zero_counts_for_empty_db(self, app):
        from extensions import db

        total, by_type, inactive = get_subscriber_stats(db)
        assert total == 0
        assert by_type == {}
        assert inactive == 0

    def test_returns_correct_counts(self, app, create_subscriber):
        from extensions import db

        create_subscriber(newsletter_type="main", active=True)
        create_subscriber(newsletter_type="main", active=True)
        create_subscriber(newsletter_type="digest", active=True)
        create_subscriber(newsletter_type="digest", active=False)

        total, by_type, inactive = get_subscriber_stats(db)
        assert total == 3
        assert by_type == {"main": 2, "digest": 1}
        assert inactive == 1

    def test_deleted_subscribers_excluded(self, app, create_subscriber):
        from datetime import datetime, timezone

        from extensions import db

        sub = create_subscriber(active=True)
        sub.deleted_at = datetime.now(timezone.utc)
        db.session.flush()

        total, by_type, inactive = get_subscriber_stats(db)
        assert total == 0
        assert by_type == {}
        assert inactive == 0


class TestCleanupInactiveSubscribers:
    @patch("services.subscribers._get_max_bounces", return_value=5)
    @patch("services.subscribers._get_inactivity_days", return_value=180)
    def test_no_subscribers_returns_zero(self, mock_bounces, mock_days, app):
        from extensions import db

        flagged, removed = cleanup_inactive_subscribers(db)
        assert flagged == 0
        assert removed == 0

    @patch("services.subscribers._get_max_bounces", return_value=5)
    @patch("services.subscribers._get_inactivity_days", return_value=180)
    def test_flags_subscriber_with_high_bounce_count(self, mock_bounces, mock_days, app, create_subscriber):
        from extensions import db

        sub = create_subscriber(active=True)
        sub.bounce_count = 6
        db.session.flush()

        flagged, removed = cleanup_inactive_subscribers(db)
        assert flagged == 1
        assert removed == 0
        assert sub.active is False

    @patch("services.subscribers._get_max_bounces", return_value=5)
    @patch("services.subscribers._get_inactivity_days", return_value=180)
    def test_flags_inactive_subscriber(self, mock_bounces, mock_days, app, create_subscriber):
        from extensions import db

        sub = create_subscriber(active=True)
        sub.last_active_at = datetime.now(timezone.utc) - timedelta(days=200)
        db.session.flush()

        flagged, removed = cleanup_inactive_subscribers(db)
        assert flagged == 1
        assert sub.active is False

    @patch("services.subscribers._get_max_bounces", return_value=5)
    @patch("services.subscribers._get_inactivity_days", return_value=180)
    def test_uses_subscribed_at_when_no_last_active(self, mock_bounces, mock_days, app, create_subscriber):
        from extensions import db

        sub = create_subscriber(active=True)
        sub.last_active_at = None
        sub.subscribed_at = datetime.now(timezone.utc) - timedelta(days=200)
        db.session.flush()

        flagged, removed = cleanup_inactive_subscribers(db)
        assert flagged == 1
        assert sub.active is False

    @patch("services.subscribers._get_max_bounces", return_value=5)
    @patch("services.subscribers._get_inactivity_days", return_value=180)
    def test_active_subscriber_not_flagged(self, mock_bounces, mock_days, app, create_subscriber):
        from extensions import db

        sub = create_subscriber(active=True)
        sub.bounce_count = 2
        sub.last_active_at = datetime.now(timezone.utc) - timedelta(days=10)
        db.session.flush()

        flagged, removed = cleanup_inactive_subscribers(db)
        assert flagged == 0
        assert sub.active is True

    @patch("services.subscribers._get_max_bounces", return_value=5)
    @patch("services.subscribers._get_inactivity_days", return_value=180)
    def test_already_inactive_subscribers_skipped(self, mock_bounces, mock_days, app, create_subscriber):
        from extensions import db

        sub = create_subscriber(active=False)
        sub.bounce_count = 10
        db.session.flush()

        flagged, removed = cleanup_inactive_subscribers(db)
        assert flagged == 0

    @patch("services.subscribers._get_max_bounces", return_value=5)
    @patch("services.subscribers._get_inactivity_days", return_value=180)
    def test_commit_failure_rolls_back(self, mock_bounces, mock_days, app, create_subscriber):
        from extensions import db

        sub = create_subscriber(active=True)
        sub.bounce_count = 10
        db.session.flush()

        with patch.object(db.session, "commit", side_effect=RuntimeError("DB error")):
            with pytest.raises(RuntimeError, match="DB error"):
                cleanup_inactive_subscribers(db)
            db.session.rollback()

    @patch("services.subscribers._get_max_bounces", return_value=2)
    @patch("services.subscribers._get_inactivity_days", return_value=30)
    def test_custom_config_thresholds(self, mock_bounces, mock_days, app, create_subscriber):
        from extensions import db

        sub1 = create_subscriber(active=True)
        sub1.bounce_count = 3
        sub2 = create_subscriber(active=True)
        sub2.last_active_at = datetime.now(timezone.utc) - timedelta(days=31)
        db.session.flush()

        flagged, removed = cleanup_inactive_subscribers(db)
        assert flagged == 2

    @patch("services.subscribers._get_max_bounces", return_value=5)
    @patch("services.subscribers._get_inactivity_days", return_value=180)
    def test_exactly_at_bounce_threshold_flagged(self, mock_bounces, mock_days, app, create_subscriber):
        from extensions import db

        sub = create_subscriber(active=True)
        sub.bounce_count = 5
        db.session.flush()

        flagged, removed = cleanup_inactive_subscribers(db)
        assert flagged == 1
        assert sub.active is False

    @patch("services.subscribers._get_max_bounces", return_value=5)
    @patch("services.subscribers._get_inactivity_days", return_value=180)
    def test_just_below_bounce_threshold_not_flagged(self, mock_bounces, mock_days, app, create_subscriber):
        from extensions import db

        sub = create_subscriber(active=True)
        sub.bounce_count = 4
        db.session.flush()

        flagged, removed = cleanup_inactive_subscribers(db)
        assert flagged == 0
        assert sub.active is True


class TestRecordBounce:
    def test_increments_bounce_count(self, app, create_subscriber):
        from extensions import db

        sub = create_subscriber()
        sub.bounce_count = 0
        db.session.flush()

        record_bounce(sub.id, db)
        assert sub.bounce_count == 1

    def test_sets_last_bounce_at(self, app, create_subscriber):
        from extensions import db

        sub = create_subscriber()
        sub.bounce_count = 0
        db.session.flush()

        record_bounce(sub.id, db)
        assert sub.last_bounce_at is not None

    def test_cumulative_bounces(self, app, create_subscriber):
        from extensions import db

        sub = create_subscriber()
        sub.bounce_count = 0
        db.session.flush()

        record_bounce(sub.id, db)
        record_bounce(sub.id, db)
        record_bounce(sub.id, db)
        assert sub.bounce_count == 3

    def test_raises_for_missing_subscriber(self, app):
        from extensions import db

        with pytest.raises(ValueError, match="Subscriber 99999 not found"):
            record_bounce(99999, db)

    def test_commit_failure_rolls_back(self, app, create_subscriber):
        from extensions import db

        sub = create_subscriber()
        sub.bounce_count = 0
        db.session.flush()

        with patch.object(db.session, "commit", side_effect=RuntimeError("DB error")):
            with pytest.raises(RuntimeError, match="DB error"):
                record_bounce(sub.id, db)
            db.session.rollback()


class TestUpdateLastActive:
    def test_sets_last_active_at(self, app, create_subscriber):
        from extensions import db

        sub = create_subscriber()
        db.session.flush()

        update_last_active(sub.id, db)
        assert sub.last_active_at is not None

    def test_overwrites_previous_timestamp(self, app, create_subscriber):
        from extensions import db

        sub = create_subscriber()
        old_time = datetime(2020, 1, 1)
        sub.last_active_at = old_time
        db.session.flush()

        update_last_active(sub.id, db)
        # SQLite strips tzinfo on round-trip, so compare naive datetimes
        assert sub.last_active_at > old_time

    def test_raises_for_missing_subscriber(self, app):
        from extensions import db

        with pytest.raises(ValueError, match="Subscriber 99999 not found"):
            update_last_active(99999, db)

    def test_commit_failure_rolls_back(self, app, create_subscriber):
        from extensions import db

        sub = create_subscriber()
        db.session.flush()

        with patch.object(db.session, "commit", side_effect=RuntimeError("DB error")):
            with pytest.raises(RuntimeError, match="DB error"):
                update_last_active(sub.id, db)
            db.session.rollback()
