"""Cross-feed clustering keeps same-event leads together and distinct events apart."""

from datetime import datetime, timezone

from services.story_clustering import (
    attach_matching_lead,
    event_fingerprint,
    register_canonical_lead,
)


def test_event_fingerprint_separates_release_update_and_correction():
    assert event_fingerprint("Acme launches Nova 3")[1] == "release"
    assert event_fingerprint("Acme updates Nova 3")[1] == "update"
    assert event_fingerprint("Acme corrects Nova 3 report")[1] == "correction"


def test_same_event_leads_share_one_candidate_and_are_idempotent(app, create_source, create_article):
    from models import StoryLead

    with app.app_context():
        first_source = create_source(source_key="cluster-source-one")
        second_source = create_source(source_key="cluster-source-two")
        article = create_article(
            source_id=first_source.id,
            original_title="Acme launches Nova 3 AI model",
            pipeline_status="researching",
        )
        article.original_published_at = datetime.now(timezone.utc).replace(tzinfo=None)
        register_canonical_lead(
            article, first_source.id, article.external_id, article.original_url,
            article.original_published_at,
        )

        candidate = attach_matching_lead(
            title="Acme launches Nova 3 AI model",
            source_id=second_source.id,
            external_id="feed-2-item-1",
            url="https://second.example/nova-3",
            published_at=article.original_published_at,
        )
        assert candidate == article.id
        assert attach_matching_lead(
            title="Acme launches Nova 3 AI model",
            source_id=second_source.id,
            external_id="feed-2-item-1",
            url="https://second.example/nova-3",
            published_at=article.original_published_at,
        ) == article.id
        assert StoryLead.query.filter_by(source_id=second_source.id, external_id="feed-2-item-1").count() == 1


def test_related_update_is_not_joined_to_release_cluster(app, create_source, create_article):
    with app.app_context():
        source = create_source(source_key="cluster-source-release")
        other = create_source(source_key="cluster-source-update")
        article = create_article(
            source_id=source.id,
            original_title="Acme launches Nova 3 AI model",
        )
        article.original_published_at = datetime.now(timezone.utc).replace(tzinfo=None)
        register_canonical_lead(article, source.id, article.external_id, article.original_url, article.original_published_at)

        candidate = attach_matching_lead(
            title="Acme updates Nova 3 AI model",
            source_id=other.id,
            external_id="feed-update",
            url="https://second.example/nova-update",
            published_at=article.original_published_at,
        )

        assert candidate is None
