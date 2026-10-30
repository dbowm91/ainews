# TTS M2 — Native Apple Silicon MLX worker, Breeze 4-bit and Opus

**Status:** IMPLEMENTED — software complete; Apple Silicon qualification **OPEN**. Code commit `d4bc9c0`.
**Parent:** [TTS roadmap](tts_audio_roadmap_20261030.md).
**Priority:** P1 first functional inference backend.
**Dependencies:** M1 authenticated job protocol and script contract.

## Outcome

Run the operator's existing **mlx-community/Breeze-TTS-2-mlx-4bit** on Apple Silicon as an optional separate process. Ainews web, Celery, Beat, Redis and ordinary Python dependencies never import MLX/Metal libraries or load model weights. An article remains published throughout model cold start, generation, encoding and retries.

## Model/runtime contract

- Use a separate macOS arm64 Python venv with pinned compatible mlx-audio, mlx, audio utilities and Hugging Face checkpoint revision; support an explicit local model directory/cache for offline startup. Initial implementation uses **from mlx_audio.tts import load; model = load("mlx-community/Breeze-TTS-2-mlx-4bit")**, then bounded calls to model.generate(text=..., instruct=..., cfg_scale=...). Verify current installed mlx-audio signature and returned GenerationResult iteration/audio/sample_rate against the pinned release before shipping. Expose INSTRUCT (not an LLM system prompt), cfg_scale (default proposal 4), optional supported reference voice/audio+exact transcript pair with rights/consent, seed if runtime supports it, and voice direction; do not assume aliases match all backends.
- Document that the 4bit repo is about 3.01 GB **checkpoint size**, not a validated peak unified-memory budget. Measure model load/cold start, warm samples, peak process RSS/unified-memory pressure, throughput and swap on the operator's actual Mac. Keep one loaded model instance, max concurrency one, a bounded memory/queue budget and explicit shutdown/signal cleanup. Never run Metal inference inside the default Linux Docker worker, nor route it through a generic text LLM provider.
- Worker polls/leases M1 jobs over authenticated private HTTPS/loopback API, receives a bounded final narration script and immutable recipe, renews claim while synthesizing and uploads the completed artifact; rate-limit/wait when idle; reconnect/retry safely after network or host sleep. No open Redis broker exposed to Mac/Internet, no requirement to mount Docker named volumes into the macOS process. Provide macOS LaunchAgent sample or manual foreground invocation, health check and offline mode. If server and Mac are different machines, require private connectivity/TLS and document certificate/auth controls.
- For lengthy scripts, render sentence-bounded chunks with consistent recipe and a narrator reference when authorized; measure speaker drift, pace and discontinuity at boundaries. Normalize mono 24 kHz PCM/WAV samples using the actual GenerationResult sample_rate and duration, add short deterministic pauses between major sections, avoid clipping and unintended silence. Use bounded per-chunk runtime, total file/audio duration and per-job execution budgets; do not retry indefinitely on deterministic generation failures.
- Prefer explicit FFmpeg subprocess (argument vector, no shell) to encode Ogg Opus, mono, e.g. 32–48 kb/s candidate bitrates and VBR. A pydub adapter is optional, not mandatory; it still needs FFmpeg. Use ffprobe and decode check to validate codec, sample rate, duration, channels, file size, nonzero signal and frame integrity. Encapsulate temporary WAV/PCM in private managed scratch and securely delete on success/failure; no intermediate WAV is externally served. Upload/ingest atomically through M1 with server-side verification of both metadata and bytes.
- Define backend protocol (capabilities: voice_design, voice_reference, cfg_scale, language, streaming, sampling) and a fake CPU backend for deterministic CI; do **not** block first MLX milestone on adding multiple inference providers. Later Qwen3-TTS/Kokoro backends remain possible, but license/controls must be verified independently and must not pretend to support Breeze-specific settings.

## Files and ownership

Add isolated package/entrypoint under tts_worker/ or services/tts_worker/ with separate optional project extra/requirements lock; services/tts/backend_protocol.py, services/tts/audio.py and CLI config/health contracts; deployment sample in systemd/ for non-MLX alternatives only and macOS LaunchAgent instructions under docs/. Keep default Dockerfile/pyproject.toml lightweight; if any optional wheel dependency is introduced, do not install it as a base dependency. Update .gitignore and backup rules for model cache, reference audio and temporary audio.

## Qualification matrix

1. CPU fake backend: stable script -> deterministic fake waveform -> FFmpeg encode -> ffprobe -> authenticated upload -> READY, with repeat requests no-op.
2. Failure injection: GPU/model unavailable, missing checkpoint, out-of-memory, model hang, worker SIGKILL, FFmpeg missing/exit nonzero, corrupt/zero-length WAV, invalid Opus, truncated upload, failed result ACK, lease expiry mid-inference and deletion before upload. Publication remains independent; state is recoverable and READY only on success.
3. Apple Silicon actual 4bit smoke: one short article, one representative long article, many chunks, mixed numbers/acronyms, a repeated voice-instruction run, optional approved reference voice. Record macOS/Apple SoC/OS/MLX versions, checkpoint SHA, real-time factor, latency, model RSS/total pressure and observed audio discontinuities.
4. Voice controls round-trip through admin recipe -> worker; config change creates new recipe identity and new job on explicit regeneration. Invalid CFG/ref settings fail validation before inference.
5. Confirm idle worker does not hold database transactions; broker/web restarts and Mac sleep/reconnect do not duplicate visible assets. Measure disk temporary usage and final Opus byte/minute against WAV; choose bitrate from listening sample.
6. License gate: Breeze self-hosted model and outputs remain research/non-commercial; operator accepts/records license policy before enabling. No inferred commercial grant from the MLX port or Apache-2.0 inference code.

## References

- 4-bit checkpoint: https://huggingface.co/mlx-community/Breeze-TTS-2-mlx-4bit
- MLX-Audio Breeze generate / instruction / CFG documentation: https://github.com/Blaizzy/mlx-audio/blob/main/docs/models/tts/breeze-tts.md
- Upstream research/non-commercial license: https://huggingface.co/BreezeBlue/Breeze-TTS-2/blob/main/LICENSE

## Implementation evidence — 2026-10-30

- **Code:** `d4bc9c0`. Added a separate native worker with lazy MLX import, pinned Breeze model revision and mlx-audio/MLX dependency lock, bounded sentence chunks, heartbeat throughout model loading and inference, a hard per-job process timeout, FFmpeg Ogg Opus encoding, authenticated transfer, and a CPU fake backend. No MLX package was added to the web/Celery dependencies.
- **Pinned API check:** inspected `mlx-audio` tag `v0.6.3`'s Breeze implementation; `generate()` exposes `text`, `instruct`, `cfg_scale` and yields result objects. The arm64 lock resolved 56 packages for Python 3.12/macOS 14+ with `mlx==0.32.4`, `mlx-audio==0.6.3`, and `huggingface-hub==1.5.0`.
- **Tests:** the 11-test TTS command in M1 passed, including deterministic fake WAV -> FFmpeg Opus -> ffprobe and authenticated upload -> READY. Ruff and mypy checks passed for changed worker modules.
- **Hardware:** **OPEN**. This workspace is Intel Mac; no MLX/Metal inference, memory/RTF benchmark, listening review, Mac sleep/wake test, or intended-host qualification is claimed. The 3.01 GB figure is checkpoint size only.
