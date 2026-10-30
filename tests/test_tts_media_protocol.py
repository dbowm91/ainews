import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg tools are optional")
def test_authenticated_result_becomes_current_range_playable_media(app, client):
    from datetime import datetime, timezone
    from extensions import db
    from models import Article, Source, TTSSettings, TTSWorkerCredential, NarrationJob
    from services.tts.jobs import ensure_narration_job_for_published
    from tts_worker.fake_backend import FakeBackend

    with app.app_context():
        db.create_all()
        app.config.update(NEWSLETTER_ARCHIVE_ENABLED=True, TTS_STORAGE_ROOT="tts-protocol-test")
        settings = TTSSettings(id=1, enabled=True, articles_enabled=True, license_accepted=True)
        token = "test-tts-worker-token-" + "x" * 32
        credential = TTSWorkerCredential(label="test worker", secret_hash=hashlib.sha256(token.encode()).hexdigest())
        source = Source(source_key="tts-protocol", name="Test source", source_type="rss")
        db.session.add_all([settings, credential, source]); db.session.flush()
        article = Article(source_id=source.id, pipeline_status="done", publicly_visible=True,
            final_article='{"headline":"Test story","tldr":"A test summary."}',
            published_at=datetime.now(timezone.utc).replace(tzinfo=None))
        db.session.add(article); db.session.commit()
        job = ensure_narration_job_for_published(article, kind="article")
        assert job is not None
        job_id = job.id
        public_id = article.public_id

    assert client.post("/internal/tts/claim").status_code == 401
    headers = {"Authorization": f"Bearer {token}"}
    claim_response = client.post("/internal/tts/claim", headers=headers)
    assert claim_response.status_code == 200
    claim = claim_response.get_json()
    assert claim["job_id"] == job_id

    backend = FakeBackend(); backend.load()
    wav_bytes, _sample_rate = backend.synthesize("A valid narration sample.")
    with tempfile.TemporaryDirectory() as directory:
        wav_path = Path(directory) / "narration.wav"
        ogg_path = Path(directory) / "narration.ogg"
        wav_path.write_bytes(wav_bytes)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(wav_path), "-ac", "1", "-ar", "24000",
            "-c:a", "libopus", "-b:a", "40k", str(ogg_path)], check=True)
        response = client.post(f"/internal/tts/{job_id}/result", data=ogg_path.read_bytes(), headers={
            **headers, "Content-Type": "audio/ogg", "X-TTS-Claim-Token": claim["claim_token"],
            "X-TTS-Script-SHA256": claim["script_sha256"],
        })
    assert response.status_code == 200, response.get_data(as_text=True)
    ready = db.session.get(NarrationJob, job_id)
    assert ready and ready.state == "ready" and ready.codec == "opus"
    media_url = f"/audio/{public_id}/{ready.audio_sha256}.ogg"
    media = client.get(media_url)
    assert media.status_code == 200
    assert media.mimetype == "audio/ogg"
    assert media.headers["Content-Disposition"].startswith("inline;")
    assert media.headers.get("ETag")
    assert client.get(media_url, headers={"Range": "bytes=0-99"}).status_code == 206
    assert client.head(media_url).status_code == 200

    article = db.session.get(Article, ready.target_id)
    article.final_article = '{"headline":"Edited story","tldr":"New text."}'
    db.session.commit()
    assert client.get(media_url).status_code == 404


def test_public_audio_is_absent_when_tts_is_disabled(app, client):
    from extensions import db
    from models import TTSSettings

    with app.app_context():
        db.create_all()
        db.session.add(TTSSettings(id=1, enabled=False, articles_enabled=False, license_accepted=False))
        db.session.commit()
    assert client.get("/audio/not-a-public-id/" + "a" * 64 + ".ogg").status_code == 404
