import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tts_worker.fake_backend import FakeBackend
from tts_worker.worker import _job_runtime_budget_seconds, _request


def test_native_worker_job_runtime_budget_is_bounded_by_recipe():
    assert _job_runtime_budget_seconds({"max_minutes": 1}) == 600
    assert _job_runtime_budget_seconds({"max_minutes": 30}) == 5700
    assert _job_runtime_budget_seconds({"max_minutes": 60}) == 10800
    with pytest.raises(ValueError):
        _job_runtime_budget_seconds({"max_minutes": 0})


def test_worker_request_allows_longer_timeout_override_for_audio_upload():
    class FakeSession:
        def request(self, method, url, **kwargs):
            return method, url, kwargs

    default = _request(FakeSession(), "POST", "http://127.0.0.1:5000", "/claim")
    upload = _request(FakeSession(), "POST", "http://127.0.0.1:5000", "/result", timeout=(10, 180))
    assert default[2]["timeout"] == (10, 60)
    assert upload[2]["timeout"] == (10, 180)


def test_fake_cpu_backend_is_repeatable_and_emits_valid_wav():
    backend = FakeBackend()
    backend.load()
    wav1, rate1 = backend.synthesize("A repeatable test sentence.")
    wav2, rate2 = backend.synthesize("A repeatable test sentence.")
    assert rate1 == rate2 == 24000
    assert hashlib.sha256(wav1).digest() == hashlib.sha256(wav2).digest()
    assert wav1[:4] == b"RIFF"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg tools are optional")
def test_fake_cpu_backend_encodes_and_probes_opus():
    backend = FakeBackend(); backend.load()
    wav_bytes, _rate = backend.synthesize("Local audio transfer acceptance test.")
    with tempfile.TemporaryDirectory() as directory:
        wav_path = Path(directory) / "test.wav"
        ogg_path = Path(directory) / "test.ogg"
        wav_path.write_bytes(wav_bytes)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav_path), "-ac", "1", "-ar", "24000", "-c:a", "libopus", "-b:a", "40k", str(ogg_path)], check=True)
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name,sample_rate,channels", "-of", "default=noprint_wrappers=1", str(ogg_path)], check=True, capture_output=True, text=True)
        assert "codec_name=opus" in probe.stdout
        assert "sample_rate=48000" in probe.stdout
        assert "channels=1" in probe.stdout
