# Optional narration (TTS)

Article and immutable newsletter edition narration is off by default. Enabling it adds no MLX dependency to the web application or ordinary Celery workers. Published text and email delivery do not wait for speech generation.

## Operator setup

1. Apply the database migrations, then open **Admin → Settings → Audio / TTS**. Confirm the Breeze research/non-commercial license before enabling global TTS and either target type. Set the model revision to a full Hugging Face commit hash. The initial pinned checkpoint is `mlx-community/Breeze-TTS-2-mlx-4bit` at `3a06d26b172ea4ae1da2f42d708383e9c79d5526`.
2. Issue a native worker credential from the settings page. The secret is displayed once; only its SHA-256 hash is stored. Put the token in a mode-600 file on the Mac. Never place it in a command line, shell history, LaunchAgent plist, or logs. Revoke it from the same page when rotating.
3. On an Apple Silicon Mac running macOS 14 or newer, install Python 3.12, FFmpeg and the optional worker requirements in a separate virtual environment:

   ```sh
   brew install ffmpeg
   python3.12 -m venv ~/ainews-tts-venv
   ~/ainews-tts-venv/bin/pip install -r tts_worker/requirements-macos-arm64.lock
   ```

   Ensure the worker's `PATH` selects Apple Silicon Homebrew tools, normally `/opt/homebrew/bin` before `/usr/local/bin`. This matters when the interactive shell itself is running under Rosetta: an x86_64 FFmpeg can otherwise be selected even though Python and MLX are native arm64.

The lock pins mlx-audio 0.6.3 and MLX 0.32.4 along with their dependencies. The upstream API returns generation-result objects with audio and sample-rate fields; the worker checks the installed `generate()` signature at runtime before using instruction and CFG controls. See the [pinned Breeze implementation](https://github.com/Blaizzy/mlx-audio/blob/v0.6.3/mlx_audio/tts/models/breeze_tts/breeze_tts.py) and [MLX-Audio API reference](https://github.com/Blaizzy/mlx-audio/blob/main/docs/api-reference/tts.md).
4. Run the worker in the foreground first, with a private service URL and token supplied through its environment:

   ```sh
   AINEWS_TTS_SERVICE=https://ainews.internal.example \
   AINEWS_TTS_TOKEN='(read from your private secret store)' \
   ~/ainews-tts-venv/bin/python tts_worker/worker.py
   ```

   Use loopback HTTP only when the Mac can reach the web app on loopback. For a separate host, use private connectivity and HTTPS with normal certificate validation; an optional CA bundle can be set through `AINEWS_TTS_CA_BUNDLE`. The worker polls for one job at a time, loads one model instance, renews its lease, and retries after connectivity failures. Each claimed job has a hard process runtime budget (three times the maximum audio duration plus five minutes, with a ten-minute minimum and three-hour cap); if native inference hangs, the worker exits so the server can recover the expired lease after the process restarts. Admin settings reports recent worker contact.

The administrator can queue a private voice preview. It uses a fixed server-owned sample, ties its freshness to the latest published article, and is served only from the authenticated admin route; preview audio is never exposed in the public article player.

The server stores verified Ogg Opus under `instance/tts` (the Docker `app-data` volume), never under `static/`. The worker resamples generated mono audio to 24 kHz before Opus encoding; Opus is reported as 48 kHz by ffprobe because that is its decoder clock. Keep the volume in backups. Its daily cleanup retains current READY assets and removes stale audio after the configured retention period. The native worker keeps temporary WAV and Opus files in a private temporary directory and removes them after each job.

## Model and output policy

Breeze weights and self-hosted outputs follow the BreezeBlue research/non-commercial license, independently of the MIT license on mlx-audio. Commercial use requires separate authorization. The admin enable switch requires an explicit license confirmation. Do not add publisher source text, personalized email HTML, citations, or arbitrary reader prompts to a job. Reference voice upload is not exposed.

The 4-bit checkpoint is reported at about 3.01 GB on disk. That is not a peak RAM requirement. Native runtime evidence on an Apple M4 Pro (24 GiB, macOS 26.6.2) used arm64 Python 3.12.16, MLX 0.32.4, mlx-audio 0.6.3 and the pinned model revision above. A cold model load including download took 135.7 seconds; a representative 5,003-character article generated 354.37 seconds of Opus in 410.9 seconds (RTF 1.16), and a frozen newsletter edition generated 149.06 seconds in 179.2 seconds (RTF 1.20). Direct listening found the output mostly good overall, though the voice/accent can seem to change unpredictably. Restart/recovery and Mac sleep/wake qualification for the canonical native-worker, non-Docker deployment remain open; Docker is a deferred deployment case. Use the CPU fake backend for repeatable integration tests.

## Private protocol

The worker uses `/internal/tts/*`, authenticated by a scoped, revocable hashed credential. Claims use short leases and one-time claim tokens. The server returns only an exact stored script and immutable recipe; completion must match the claim, script digest, current target revision, current speech recipe, policy, and encoded media checks. Upload is bounded and streamed into a private temporary file before atomic rename. Public media URLs include the opaque target ID and audio digest; the route checks current publication, policy, file size and content digest for every request. Disabled, stale, missing, or corrupt assets return 404.

No Redis broker is exposed to the Mac, and no request handler, editorial stage, publication transaction, or email-delivery task performs TTS inference.
