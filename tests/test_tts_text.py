import json

import pytest

from services.tts.text import render_article_script, render_edition_script, split_script


def test_article_script_is_deterministic_and_excludes_source_urls_and_citations():
    article = json.dumps({
        "headline": "New model arrives [1]",
        "tldr": "A major release is available at https://publisher.example/item.",
        "why_it_matters": "It changes the field for researchers.",
        "key_takeaways": ["Teams can test the new model."],
        "body": "<p>The model is available now.</p> See https://example.com [2]",
        "what_to_watch": "Adoption over the next year.",
    })
    first = render_article_script(article)
    assert first == render_article_script(article)
    assert "publisher.example" not in first
    assert "example.com" not in first
    assert "[1]" not in first and "[2]" not in first
    assert "The model is available now." in first
    assert "Adoption over the next year." in first


def test_edition_script_uses_frozen_ordered_items_without_citation_urls():
    script = render_edition_script("Weekly AI", "A short summary", [
        {"position": 2, "headline": "Second story", "why_it_matters": "Second matters", "paragraph": "Later."},
        {"position": 1, "headline": "First story", "why_it_matters": "First matters", "paragraph": "Earlier."},
    ])
    assert script.index("First story") < script.index("Second story")
    assert "https://" not in script


def test_script_limits_and_chunking_are_bounded_and_repeatable():
    with pytest.raises(ValueError):
        render_edition_script("", "", [], max_chars=20)
    source = "First sentence. " + ("word " * 400) + "Last sentence."
    chunks = split_script(source, max_chars=250)
    assert chunks == split_script(source, max_chars=250)
    assert all(len(chunk) <= 250 for chunk in chunks)
    assert "Last sentence." in chunks[-1]


def test_disabled_by_default_and_enabled_publication_job_is_idempotent(app):
    from datetime import datetime, timezone
    from extensions import db
    from models import Article, NarrationJob, Source, TTSSettings
    from services.tts.jobs import ensure_narration_job_for_published, queue_voice_preview

    with app.app_context():
        db.create_all()
        source = Source(source_key="tts-test", name="Test", source_type="rss")
        db.session.add(source); db.session.flush()
        article = Article(source_id=source.id, pipeline_status="done", publicly_visible=True,
            final_article=json.dumps({"headline": "A test", "tldr": "A summary.", "body": "A detailed body."}),
            published_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db.session.add(article); db.session.commit()
        app.config.update(TTS_ENABLED=False, TTS_ARTICLES_ENABLED=False)
        assert ensure_narration_job_for_published(article) is None
        db.session.add(TTSSettings(id=1, enabled=True, articles_enabled=True, license_accepted=True))
        db.session.commit()
        first = ensure_narration_job_for_published(article)
        second = ensure_narration_job_for_published(article)
        assert first is not None and first.id == second.id
        assert first.target_public_id == article.public_id
        assert NarrationJob.query.count() == 1
        assert "A detailed body." in first.script
        preview = queue_voice_preview(article)
        assert preview is not None and preview.recipe["admin_preview"] is True
        assert preview.id != first.id and preview.script.startswith("This is a short AInews narration preview.")
        assert queue_voice_preview(article).id == preview.id
        assert NarrationJob.query.count() == 2
        from services.tts.worker_protocol import claim_next
        assert claim_next()["recipe"].get("admin_preview") is None
        assert claim_next()["recipe"]["admin_preview"] is True


def test_worker_claim_is_single_owner_for_current_job(app):
    from datetime import datetime, timezone
    from extensions import db
    from models import Article, NarrationJob, Source, TTSSettings
    from services.tts.jobs import ensure_narration_job_for_published
    from services.tts.worker_protocol import claim_next, owns_claim
    import json

    with app.app_context():
        db.create_all()
        app.config.update(TTS_ENABLED=False)
        db.session.add(TTSSettings(id=1, enabled=True, articles_enabled=True, license_accepted=True))
        source = Source(source_key="tts-claim-test", name="Test", source_type="rss")
        db.session.add(source); db.session.flush()
        article = Article(source_id=source.id, pipeline_status="done", publicly_visible=True,
            final_article=json.dumps({"headline": "Claim", "tldr": "Test."}), published_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db.session.add(article); db.session.commit()
        job = ensure_narration_job_for_published(article)
        assert job
        claim = claim_next()
        assert claim and claim["job_id"] == job.id
        claimed = db.session.get(NarrationJob, job.id)
        assert claimed and owns_claim(claimed, claim["claim_token"])
        assert claim_next() is None


def test_published_edition_job_uses_frozen_ordered_snapshot_without_email_dependency(app):
    from datetime import datetime, timezone
    from extensions import db
    from models import NewsletterEdition, NewsletterEditionItem, NewsletterProfile, NarrationJob, TTSSettings
    from services.tts.jobs import ensure_narration_job_for_published

    with app.app_context():
        db.create_all()
        app.config.update(NEWSLETTER_ARCHIVE_ENABLED=True, TTS_ENABLED=False)
        profile = NewsletterProfile(key="main", scope="global", title="AInews")
        settings = TTSSettings(id=1, enabled=True, editions_enabled=True, license_accepted=True)
        db.session.add_all([profile, settings]); db.session.flush()
        edition = NewsletterEdition(profile_id=profile.id, profile_key="main", profile_title="AInews",
            occurrence_key="tts-edition-fixture", status="published", subject="Weekly briefing",
            summary="The week's developments.", published_at=datetime.now(timezone.utc).replace(tzinfo=None),
            email_requested=True)
        edition.items = [
            NewsletterEditionItem(article_public_id="article-public-1", position=1,
                headline="Frozen headline", why_it_matters="Frozen context.", paragraph="Frozen paragraph.",
                canonical_url="https://example.test/story", source_url="https://source.test/story"),
        ]
        db.session.add(edition); db.session.commit()

        job = ensure_narration_job_for_published(edition, kind="edition")
        assert job is not None
        assert job.state == "pending"
        assert job.target_kind == "edition"
        assert "Frozen headline" in job.script and "Frozen paragraph." in job.script
        assert "source.test" not in job.script
        assert edition.email_requested is True
        assert NarrationJob.query.count() == 1
        assert ensure_narration_job_for_published(edition, kind="edition").id == job.id
