"""Only articles with a publication record may be exposed publicly."""

from datetime import datetime, timezone


def _published_at():
    return datetime.now(timezone.utc)


def test_public_feed_tag_rss_and_sitemap_exclude_unpublished_articles(
    client, create_article, create_source, create_tag,
):
    source = create_source()
    published = create_article(
        source=source,
        original_title="Visible Published Story",
        pipeline_status="done",
        category="ai",
        published_at=_published_at(),
    )
    unqualified_done = create_article(
        source=source,
        original_title="Hidden Done Without Publication",
        pipeline_status="done",
        category="ai",
    )
    unqualified_done.publicly_visible = False
    skipped = create_article(
        source=source,
        original_title="Hidden Skipped Story",
        pipeline_status="skipped",
        category="ai",
        published_at=_published_at(),
    )
    active_with_timestamp = create_article(
        source=source,
        original_title="Hidden Active Story",
        pipeline_status="writing",
        category="ai",
        published_at=_published_at(),
    )
    tag = create_tag(name="visibility", slug="visibility")
    for article in (published, unqualified_done, skipped, active_with_timestamp):
        article.tags.append(tag)

    from extensions import db

    db.session.commit()

    for path in ("/", "/topic/ai", "/tag/visibility"):
        response = client.get(path)
        body = response.get_data(as_text=True)
        assert response.status_code == 200
        assert "Visible Published Story" in body
        assert "Hidden Done Without Publication" not in body
        assert "Hidden Skipped Story" not in body
        assert "Hidden Active Story" not in body

    rss = client.get("/feed").get_data(as_text=True)
    assert "Visible Published Story" in rss
    assert "Hidden Done Without Publication" not in rss
    assert "Hidden Skipped Story" not in rss
    assert "Hidden Active Story" not in rss

    sitemap = client.get("/sitemap.xml").get_data(as_text=True)
    assert f"/article/{published.public_id}" in sitemap
    assert f"/article/{unqualified_done.public_id}" not in sitemap
    assert f"/article/{skipped.public_id}" not in sitemap
    assert f"/article/{active_with_timestamp.public_id}" not in sitemap


def test_public_search_and_article_links_require_published_status(
    client, create_article, create_source,
):
    source = create_source()
    published = create_article(
        source=source,
        original_title="visibilityprobe Published Result",
        pipeline_status="done",
        published_at=_published_at(),
    )
    unqualified = create_article(
        source=source,
        original_title="visibilityprobe Unpublished Result",
        pipeline_status="done",
    )
    unqualified.publicly_visible = False
    skipped = create_article(
        source=source,
        original_title="visibilityprobe Skipped Result",
        pipeline_status="skipped",
        published_at=_published_at(),
    )

    from extensions import db

    db.session.commit()

    response = client.get("/?q=visibilityprobe")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "visibilityprobe Published Result" in body
    assert "visibilityprobe Unpublished Result" not in body
    assert "visibilityprobe Skipped Result" not in body

    assert client.get(f"/article/{unqualified.public_id}").status_code == 404
    assert client.get(f"/article/{skipped.public_id}").status_code == 404
    assert client.get(f"/article/{published.public_id}").status_code == 200
    assert client.get(f"/article/{published.id}").status_code == 404
    assert client.get(f"/s/{unqualified.short_id}").status_code == 404
    assert client.get(f"/a/{unqualified.short_id}").status_code == 404
