"""Single-job-at-a-time native MLX worker; MLX is imported only after claiming work."""
from __future__ import annotations

import argparse
import inspect
import logging
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import requests

LOG = logging.getLogger("ainews.tts_worker")
MODEL_ID = "mlx-community/Breeze-TTS-2-mlx-4bit"
MODEL_REVISION = "3a06d26b172ea4ae1da2f42d708383e9c79d5526"
_stop = False


def _on_signal(_signum, _frame):
    global _stop
    _stop = True


def _generate(model, text: str, instruction: str, cfg_scale: float) -> tuple[np.ndarray, int]:
    signature = inspect.signature(model.generate)
    kwargs: dict[str, str | float] = {"text": text}
    if "instruct" not in signature.parameters or "cfg_scale" not in signature.parameters:
        raise RuntimeError("installed Breeze API must expose instruct and cfg_scale controls")
    kwargs["instruct"] = instruction
    kwargs["cfg_scale"] = cfg_scale
    results = model.generate(**kwargs)
    waves: list[np.ndarray] = []
    sample_rate = 0
    for result in results:
        sample_rate = int(result.sample_rate)
        wave = np.asarray(result.audio, dtype=np.float32).reshape(-1)
        if wave.size:
            waves.append(wave)
    if not waves or sample_rate <= 0:
        raise RuntimeError("model returned no valid audio")
    return np.concatenate(waves), sample_rate


def _load_model(model_id: str, revision: str, local_dir: str | None):
    from huggingface_hub import snapshot_download
    from mlx_audio.tts import load
    source = local_dir or snapshot_download(repo_id=model_id, revision=revision)
    model = load(source)
    signature = inspect.signature(model.generate)
    if "text" not in signature.parameters:
        raise RuntimeError("mlx-audio generate(text=...) signature is unsupported")
    return model


def _request(session: requests.Session, method: str, base: str, path: str, **kwargs):
    return session.request(method, f"{base.rstrip('/')}{path}", timeout=(10, 60), **kwargs)


def _split(text: str, size: int = 1200) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    out: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > size:
            cut = sentence.rfind(" ", 0, size + 1)
            cut = cut if cut > 0 else size
            out.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > size:
            out.append(current); current = sentence
        else:
            current = candidate
    if current:
        out.append(current)
    return out


def _job_runtime_budget_seconds(recipe: dict) -> int:
    """Hard bound a job even when native inference stops making progress.

    Allow up to three times the configured maximum audio duration plus five
    minutes for model warmup, encoding, and transfer, capped at three hours.
    The server lease is recovered after this process exits.
    """
    max_minutes = int(recipe.get("max_minutes", 30))
    if not 1 <= max_minutes <= 60:
        raise ValueError("job recipe max_minutes is outside the supported range")
    return min(3 * 60 * 60, max(10 * 60, max_minutes * 3 * 60 + 5 * 60))


def _start_heartbeat(session: requests.Session, base: str, job: dict) -> tuple[threading.Event, threading.Thread]:
    done = threading.Event()

    def heartbeat_loop():
        with requests.Session() as heartbeat_session:
            heartbeat_session.headers["Authorization"] = session.headers["Authorization"]
            heartbeat_session.verify = session.verify
            while not done.wait(90):
                try:
                    _request(heartbeat_session, "POST", base, f"/internal/tts/{job['job_id']}/heartbeat",
                        json={"claim_token": job["claim_token"]}).raise_for_status()
                except Exception:  # noqa: BLE001 - lease protocol recovers missed heartbeat
                    LOG.warning("Heartbeat failed for job %s; server lease recovery remains authoritative", job["job_id"])

    thread = threading.Thread(target=heartbeat_loop, name="tts-heartbeat", daemon=True)
    thread.start()
    return done, thread


def _start_watchdog(job: dict) -> threading.Timer:
    budget_seconds = _job_runtime_budget_seconds(job["recipe"])

    def stop_over_budget_job():
        LOG.critical("Job %s exceeded its %ss runtime budget; exiting for lease recovery", job["job_id"], budget_seconds)
        os._exit(124)

    watchdog = threading.Timer(budget_seconds, stop_over_budget_job)
    watchdog.daemon = True
    watchdog.start()
    return watchdog


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", default=os.environ.get("AINEWS_TTS_SERVICE", ""))
    parser.add_argument("--token", default=os.environ.get("AINEWS_TTS_TOKEN", ""))
    parser.add_argument("--model-dir", default=os.environ.get("AINEWS_TTS_MODEL_DIR"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--poll-seconds", type=float, default=8)
    parser.add_argument("--ca-bundle", default=os.environ.get("AINEWS_TTS_CA_BUNDLE"))
    args = parser.parse_args()
    if not args.service or len(args.token) < 32:
        parser.error("configure --service and a private worker token (at least 32 characters)")
    if not args.service.startswith("https://") and not args.service.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
        parser.error("service URL must use HTTPS, except loopback HTTP")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {args.token}"
    session.verify = args.ca_bundle or True
    signal.signal(signal.SIGINT, _on_signal); signal.signal(signal.SIGTERM, _on_signal)
    model = None
    loaded_key = None
    with tempfile.TemporaryDirectory(prefix="ainews-tts-") as directory:
        scratch = Path(directory)
        os.chmod(scratch, 0o700)
        while not _stop:
            try:
                response = _request(session, "POST", args.service, "/internal/tts/claim")
                if response.status_code == 204:
                    time.sleep(max(2, args.poll_seconds)); continue
                response.raise_for_status()
                job = response.json()
                watchdog = _start_watchdog(job)
                done, heartbeat_thread = _start_heartbeat(session, args.service, job)
                try:
                    model_id = job["recipe"]["model"]
                    revision = job["recipe"]["checkpoint_revision"]
                    if args.model and args.model != model_id or args.revision and args.revision != revision:
                        raise RuntimeError("worker model pin does not match the server's immutable job recipe")
                    key = (model_id, revision)
                    if key != loaded_key:
                        model = _load_model(model_id, revision, args.model_dir)
                        loaded_key = key
                    _process_job(session, args.service, model, scratch, job)
                finally:
                    watchdog.cancel()
                    done.set(); heartbeat_thread.join(timeout=2)
            except Exception:
                LOG.exception("Worker poll/inference failed; retrying")
                time.sleep(max(5, args.poll_seconds))
    return 0


def _process_job(session, base, model, scratch, job):
    token = job["claim_token"]
    started = time.monotonic()
    try:
        chunks = []
        rate = None
        for text in _split(job["script"]):
            _request(session, "POST", base, f"/internal/tts/{job['job_id']}/heartbeat", json={"claim_token": token}).raise_for_status()
            wave, got_rate = _generate(model, text, job["recipe"]["instruction"], float(job["recipe"]["cfg_scale"]))
            if rate is not None and got_rate != rate:
                raise RuntimeError("chunk sample rate changed")
            rate = rate or got_rate
            chunks.extend((wave, np.zeros(int(rate * .25), dtype=np.float32)))
        import scipy.io.wavfile
        wav = scratch / f"{job['job_id']}.wav"; ogg = scratch / f"{job['job_id']}.ogg"
        scipy.io.wavfile.write(str(wav), rate, np.clip(np.concatenate(chunks[:-1]), -1, 1))
        bitrate = int(job["recipe"].get("opus_bitrate", 40))
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(wav), "-ac", "1", "-ar", "24000", "-c:a", "libopus", "-b:a", f"{bitrate}k", "-vbr", "on", str(ogg)], check=True, timeout=300)
        with ogg.open("rb") as audio:
            _request(session, "POST", base, f"/internal/tts/{job['job_id']}/result", data=audio,
                headers={"Content-Type": "audio/ogg", "X-TTS-Claim-Token": token,
                         "X-TTS-Script-SHA256": job["script_sha256"]}, timeout=(10, 180)).raise_for_status()
        LOG.info("Job %s synthesized and transferred in %.1fs; %d chunks", job["job_id"], time.monotonic() - started, len(chunks) // 2)
    except Exception as exc:
        LOG.exception("Narration job %s failed", job["job_id"])
        try:
            _request(session, "POST", base, f"/internal/tts/{job['job_id']}/fail", json={"claim_token": token, "error_code": type(exc).__name__[:64]})
        except Exception:  # noqa: BLE001 - lease expiry recovers unavailable failure endpoint
            pass
    finally:
        (scratch / f"{job['job_id']}.wav").unlink(missing_ok=True); (scratch / f"{job['job_id']}.ogg").unlink(missing_ok=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
