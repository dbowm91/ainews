"""Private immutable Opus asset storage and media verification."""
from __future__ import annotations

import hashlib
import os
import secrets
import subprocess
import tempfile
from pathlib import Path

from flask import current_app


def storage_root() -> Path:
    configured = Path(str(current_app.config.get("TTS_STORAGE_ROOT", "tts")))
    instance = Path(current_app.instance_path).resolve()
    candidate = configured if configured.is_absolute() else instance / configured
    if candidate.is_symlink():
        raise ValueError("TTS storage root cannot be a symlink")
    root = candidate.resolve()
    if not root.is_relative_to(instance):
        raise ValueError("TTS storage must remain inside the application instance directory")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def validate_opus(path: Path) -> dict:
    size = path.stat().st_size
    if not size or size > int(current_app.config.get("TTS_MAX_UPLOAD_BYTES", 24 * 1024 * 1024)):
        raise ValueError("audio_size_invalid")
    try:
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
            "stream=codec_name,sample_rate,channels:format=format_name,duration", "-of", "default=noprint_wrappers=1", str(path)],
            capture_output=True, text=True, timeout=15, check=True)
    except FileNotFoundError as exc:
        raise ValueError("ffprobe_unavailable") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError("audio_probe_invalid") from exc
    info = dict(line.split("=", 1) for line in probe.stdout.splitlines() if "=" in line)
    duration = float(info.get("duration", "0"))
    # ffprobe reports Opus at its 48 kHz decode clock, even when the input
    # waveform was resampled to 24 kHz before encoding.
    if info.get("codec_name") != "opus" or info.get("format_name") != "ogg" or info.get("sample_rate") != "48000" or info.get("channels") != "1":
        raise ValueError("audio_format_invalid")
    from services.tts.settings import value
    max_duration = min(int(current_app.config.get("TTS_MAX_DURATION_SECONDS", 1800)), int(value("max_minutes", 30)) * 60)
    if duration <= 0 or duration > max_duration:
        raise ValueError("audio_duration_invalid")
    check = subprocess.run(["ffmpeg", "-v", "info", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=60)
    if check.returncode:
        raise ValueError("audio_decode_invalid")
    if "mean_volume: -inf dB" in check.stderr:
        raise ValueError("audio_silence_invalid")
    hasher = hashlib.sha256()
    with path.open("rb") as audio:
        for chunk in iter(lambda: audio.read(64 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    return {"sha256": digest, "duration_seconds": duration, "channels": 1, "sample_rate": 48000,
            "codec": "opus", "byte_size": size}


def store_upload(stream) -> tuple[str, Path, dict]:
    root = storage_root()
    fd, temp_name = tempfile.mkstemp(prefix="upload-", suffix=".part", dir=root)
    total = 0
    try:
        with os.fdopen(fd, "wb") as output:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > int(current_app.config.get("TTS_MAX_UPLOAD_BYTES", 24 * 1024 * 1024)):
                    raise ValueError("audio_size_invalid")
                output.write(chunk)
            output.flush(); os.fsync(output.fileno())
        temp_path = Path(temp_name)
        metadata = validate_opus(temp_path)
        key = secrets.token_urlsafe(24)
        final = root / f"{key}.ogg"
        os.replace(temp_path, final)
        os.chmod(final, 0o600)
        return key, final, metadata
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def get_audio_path(key: str) -> Path | None:
    if not key or "/" in key or "\\" in key or not all(c.isalnum() or c in "-_" for c in key):
        return None
    path = storage_root() / f"{key}.ogg"
    return path if path.is_file() else None


def verify_stored_asset(job) -> Path | None:
    """Recheck ready asset bytes, size and SHA before rendering or serving."""
    path = get_audio_path(job.storage_key or "")
    if path is None:
        return None
    try:
        stat = path.stat()
        if stat.st_size != job.byte_size or stat.st_size <= 0:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(64 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != job.audio_sha256:
            return None
    except OSError:
        return None
    return path
