# Production Deployment Guide

Deploy ainews to a production server using the installer (recommended), Docker, or bare metal with systemd.

## Option C: Installer (Recommended for Production)

The recommended installation path uses the channel-aware installer:

```bash
curl -fsSL https://raw.githubusercontent.com/dbowm91/ainews/main/scripts/install.sh | bash
ainews onboard
ainews start
```

### Supported Platforms

| Platform | Architecture | Status |
|----------|-------------|--------|
| Linux | x86_64 | Supported |
| Linux | aarch64/arm64 | Supported |
| macOS | arm64 | Supported |
| Windows | — | Use WSL |

### Installation Modes

**User installation** (default, no root required):
- App: `~/.local/share/ainews/app/`
- Config: `~/.config/ainews/`
- State: `~/.local/state/ainews/`
- CLI: `~/.local/bin/ainews`

**System installation** (requires root):
- App: `/opt/ainews/`
- Config: `/etc/ainews/`
- State: `/var/lib/ainews/`
- CLI: `/usr/local/bin/ainews`

### Channel Selection

| Channel | Description | Default |
|---------|-------------|---------|
| `stable` | Latest non-prerelease GitHub release | Yes |
| `prerelease` | Latest prerelease | No |
| `main` | Exact commit SHA (dev/eval only) | No |

### Non-Interactive Installation

```bash
AINEWS_BOOTSTRAP_ADMIN_PASSWORD_FILE=/run/secrets/ainews-admin \
  ./scripts/install.sh --non-interactive --bootstrap ./bootstrap.yaml --start
```

### Docker-Absent Installation

The installer succeeds without Docker when `--start` is not requested. Install metadata is written, and onboarding can be deferred. After Docker is available, run `ainews start` to complete setup.

## Option A: Docker (Recommended)

### Prerequisites

- Docker and Docker Compose
- A `.env` file with production settings

### Required Secrets

| Variable | How to generate |
|----------|----------------|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_PASSWORD` | `python scripts/hash_password.py` |
| `CELERY_TASK_SECRET` | `python -c "import secrets; print(secrets.token_hex(32))"` |

### Quick Deploy

```bash
git clone https://github.com/dbowm91/ainews.git
cd ainews
cp .env.example .env
```

Edit `.env`:
```bash
FLASK_CONFIG=production
SECRET_KEY=<64-char hex string>
ADMIN_PASSWORD=<hashed password from hash_password.py>
CELERY_TASK_SECRET=<64-char hex string>
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
```

#### Choose an LLM Provider

**Option 1: Cloud provider (simplest)**
```yaml
# providers.yaml
default_provider: openai
providers:
  - id: openai
    type: openai
    enabled: true
    config:
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
```
Set `OPENAI_API_KEY=sk-...` in `.env`.

**Option 2: Ollama as a Compose service**
```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d
```
This adds an Ollama container accessible at `http://ollama:11434`. Update `providers.yaml`:
```yaml
default_provider: ollama-local
providers:
  - id: ollama-local
    type: ollama
    enabled: true
    config:
      host: "http://ollama:11434"
      model: "qwen3:8b"
```
Pull the model on first run: `docker compose exec ollama ollama pull qwen3:8b`

**Option 3: Host Ollama (advanced)**
If Ollama runs on the host machine, use `host.docker.internal`:
```yaml
config:
  host: "http://host.docker.internal:11434"
```
On Linux, this may require `extra_hosts` in `docker-compose.yml`:
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

> **Warning:** `http://localhost:11434` does NOT work from inside Docker containers. The app will start but LLM calls will fail. Use one of the options above.

### Start and Verify

```bash
docker compose up -d
docker compose ps
curl http://localhost:5000/health
```

### Production Config Validation

In production mode (`FLASK_CONFIG=production`), `ProductionConfig.validate()` runs at startup and **prevents the app from starting** if any check fails:

- **Required secrets:** SECRET_KEY (64-char hex), ADMIN_PASSWORD (hashed), CELERY_TASK_SECRET (>=32 chars)
- **LLM Providers:** At least one provider enabled. `default_provider` must exist and be enabled. Enabled cloud providers must have valid API keys. Unknown provider types are rejected.
- **Debug mode:** Must be disabled (`DEBUG=False`)
- **Session security:** `SESSION_COOKIE_SECURE` must be True

Fix the reported issue and restart. See [docs/configuration.md](docs/configuration.md) for full reference.

### Docker with Ollama

**Important:** `localhost` inside a Docker container refers to the container itself, not the host machine. If Ollama runs on the host, the app containers cannot reach it at `localhost:11434`.

#### Mode A: Ollama as Compose service (recommended for self-hosted)

```bash
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d
docker compose exec ollama ollama pull qwen3:8b
```

Set `providers.yaml` host to `http://ollama:11434`. The Ollama container joins the same Docker network and is accessible by service name.

#### Mode B: Host Ollama

If you prefer Ollama on the host, configure `providers.yaml` with `http://host.docker.internal:11434`.

- **macOS/Windows:** Docker Desktop supports `host.docker.internal` by default.
- **Linux:** Add `extra_hosts: ["host.docker.internal:host-gateway"]` to each service that needs host access.

#### Mode C: Cloud provider

No Ollama needed. Set an API key for OpenAI, Anthropic, or another cloud provider in `.env` and enable it in `providers.yaml`.

#### Mode D: Bare metal

`http://localhost:11434` is correct when running the app directly on the host with Ollama.

### Docker Services

| Service | Description |
|---------|-------------|
| `db-migrate` | Runs `flask db upgrade` on startup (exits after) |
| `web` | Flask app via Granian |
| `celery-worker` | Background task processor |
| `celery-beat` | Scheduled task runner |
| `redis` | Message broker |

### Docker Management

```bash
# View logs
docker compose logs -f web
docker compose logs -f celery-worker

# Restart after code update
docker compose pull
docker compose up -d --build

# Stop everything
docker compose down

# Stop and remove data volumes
docker compose down -v
```

### Docker with Nginx Reverse Proxy

Place Nginx on the host (not in Docker) for SSL termination:

```nginx
server {
    listen 80;
    server_name news.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name news.example.com;

    ssl_certificate /etc/ssl/certs/news.example.com.crt;
    ssl_certificate_key /etc/ssl/private/news.example.com.key;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Static files — serve directly via volume mount
    # Adjust the alias path to match your deployment directory
    location /static/ {
        alias /opt/ainews/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Application
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    access_log /var/log/nginx/ainews-access.log;
    error_log /var/log/nginx/ainews-error.log;
}
```

---

## Option B: Bare Metal (systemd)

### System Requirements

| | Minimum | Recommended |
|---|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 2 GB | 4 GB |
| Storage | 20 GB | 50 GB SSD |
| OS | Ubuntu 22.04+ | Ubuntu 24.04 LTS |

### Automated Install

```bash
sudo bash scripts/install.sh
```

The install script:
1. Creates `ainews` system user
2. Installs Python, Redis, Nginx
3. Sets up virtual environment
4. Creates `.env` with hashed admin password
5. Initializes the database
6. Installs and enables systemd services

### Manual Install

#### 1. Create user and install dependencies

```bash
sudo useradd --system --shell /bin/false --home-dir /opt/ainews --create-home ainews
sudo apt update && sudo apt install python3.12 python3.12-venv redis-server nginx
sudo systemctl enable --now redis-server
```

#### 2. Set up application

```bash
sudo -u ainews -i
cd /opt/ainews
git clone https://github.com/dbowm91/ainews.git .
python3.12 -m venv .venv
source .venv/bin/activate
uv sync
uv pip install "granian>=1.0.0,<2"
```

#### 3. Configure

```bash
cp .env.example .env
# Edit .env with production values
python scripts/hash_password.py   # Generate hashed admin password
chmod 600 .env
```

#### 4. Install systemd services

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ainews-web ainews-celery-worker ainews-celery-beat
sudo systemctl start ainews-web ainews-celery-worker ainews-celery-beat
```

### Systemd Services

| Service | Description | Memory Limit |
|---------|-------------|-------------|
| `ainews-web` | Granian ASGI server | 1 GB |
| `ainews-celery-worker` | Celery task processor | 2 GB |
| `ainews-celery-beat` | Celery beat scheduler | 512 MB |

### Managing Services

```bash
# Status
systemctl status ainews-web

# Restart after code update
sudo bash scripts/deploy.sh

# Rollback if something breaks
sudo bash scripts/deploy.sh --rollback

# Logs
journalctl -u ainews-web -f
journalctl -u ainews-celery-worker -f
```

### Granian Tuning

Adjust worker count based on CPU:
```
workers = (2 × CPU_CORES) + 1
```

Edit the systemd service:
```bash
sudo systemctl edit ainews-web
```

Each worker uses ~100-200 MB RAM.

### Bare Metal Nginx Config

```nginx
server {
    listen 80;
    server_name news.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name news.example.com;

    ssl_certificate /etc/ssl/certs/news.example.com.crt;
    ssl_certificate_key /etc/ssl/private/news.example.com.key;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Static files — serve directly, bypass Flask
    location /static/ {
        alias /opt/ainews/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Application
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    access_log /var/log/nginx/ainews-access.log;
    error_log /var/log/nginx/ainews-error.log;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/ainews /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## Database Backup

### Automated backup script

```bash
bash scripts/backup.sh
```

Backs up SQLite with WAL checkpoint, compresses, and rotates after 30 days.

### Cron schedule

```cron
# Daily backup at 2 AM
0 2 * * * /opt/ainews/scripts/backup.sh >> /var/log/ainews-backup.log 2>&1
```

### Restore from backup

```bash
# Stop services first
sudo systemctl stop ainews-web ainews-celery-worker ainews-celery-beat

# Restore
gunzip -c /opt/ainews/backups/ainews-20240101-020000.db.gz > /opt/ainews/instance/ainews.db
sudo chown ainews:ainews /opt/ainews/instance/ainews.db

# Start services
sudo systemctl start ainews-web ainews-celery-worker ainews-celery-beat
```

---

## Monitoring

### Health check

```bash
# Public (no auth)
curl http://localhost:5000/health

# Admin (requires session auth or API token)
# Option 1: API token (recommended for scripts)
curl -H "Authorization: Bearer ak_<prefix>.<secret>" http://localhost:5000/admin/api/health

# Option 2: Session auth (log in via browser, then use browser cookies)
curl -b cookies.txt http://localhost:5000/admin/api/health
```

### Service status

```bash
systemctl is-active ainews-web ainews-celery-worker ainews-celery-beat
```

### Logs

```bash
# All services
journalctl -u ainews-* -f

# Errors only
journalctl -u ainews-web -p err
```

---

## Systemd Service Configuration

Create `/etc/systemd/system/ainews-web.service`:

```ini
[Unit]
Description=AI News Flask Application
After=network.target redis.service
Wants=redis.service

[Service]
Type=notify
User=ainews
Group=ainews
WorkingDirectory=/opt/ainews
Environment="PATH=/opt/ainews/.venv/bin"
Environment="FLASK_CONFIG=production"
ExecStart=/opt/ainews/.venv/bin/granian --host 127.0.0.1 --port 5000 --workers 5 --threads 4 --interface asgi run:app
Restart=always
RestartSec=5
MemoryMax=1G
TimeoutStartSec=30
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/ainews-celery-worker.service`:

```ini
[Unit]
Description=AI News Celery Worker
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=ainews
Group=ainews
WorkingDirectory=/opt/ainews
Environment="PATH=/opt/ainews/.venv/bin"
Environment="FLASK_CONFIG=production"
ExecStart=/opt/ainews/.venv/bin/celery -A celery_app worker --loglevel=info --concurrency=4
Restart=always
RestartSec=10
MemoryMax=2G
TimeoutStartSec=60
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/ainews-celery-beat.service`:

```ini
[Unit]
Description=AI News Celery Beat Scheduler
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=ainews
Group=ainews
WorkingDirectory=/opt/ainews
Environment="PATH=/opt/ainews/.venv/bin"
Environment="FLASK_CONFIG=production"
ExecStart=/opt/ainews/.venv/bin/celery -A celery_app beat --loglevel=info
Restart=always
RestartSec=10
MemoryMax=512M
TimeoutStartSec=30
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

Reload systemd after creating services:
```bash
sudo systemctl daemon-reload
```

### Automated Service Management

The `ainews service` commands provide automated systemd unit generation and management:

```bash
# Preview generated unit files
ainews service render --systemd

# Install systemd units (user scope)
ainews service install --systemd --enable

# Install and start immediately
ainews service install --systemd --enable --start

# Validate configuration
ainews service validate --systemd

# Check service status
ainews service status

# Restart services
ainews service restart

# Remove installed units
ainews service remove
```

For Docker Compose deployments:

```bash
ainews service render --systemd --profile docker_compose
ainews service install --systemd --profile docker_compose --enable
```

### Systemd Hardening

Generated units include comprehensive security hardening:

| Directive | Purpose |
|-----------|---------|
| `NoNewPrivileges=true` | Prevent privilege escalation |
| `PrivateTmp=true` | Isolated `/tmp` directory |
| `ProtectSystem=strict` | Read-only `/usr`, `/boot`, `/efi` |
| `ProtectHome=true` | Hide `/home`, `/root`, `/run/user` |
| `UMask=0027` | Restrict file permissions |
| `CapabilityBoundingSet=` | Drop all Linux capabilities |
| `RestrictNamespaces=true` | Prevent namespace creation |
| `RestrictRealtime=true` | Prevent real-time scheduling |
| `RestrictSUIDSGID=true` | Prevent SUID/SGID files |
| `MemoryDenyWriteExecute=true` | Prevent W^X violations |
| `LockPersonality=true` | Lock execution domain |
| `SystemCallArchitectures=native` | Prevent ABI emulation |
| `PrivateDevices=true` | Hide physical devices |
| `ProtectKernelTunables=true` | Protect `/proc`, `/sys` |
| `ProtectKernelModules=true` | Prevent module loading |
| `ProtectControlGroups=true` | Protect cgroup hierarchy |
| `ProtectClock=true` | Prevent clock changes |
| `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX` | Limit socket types |

**Docker Compose compatibility:** For containerized deployments, some hardening directives may need adjustment. Use `--profile docker_compose` to generate compatible units.

### Installation Safety

The installation process includes multiple safety mechanisms:

1. **Validation:** Comprehensive checks before installation
2. **Diff preview:** Shows exactly what will change
3. **Atomic writes:** Files are written atomically with rollback on failure
4. **Content tracking:** SHA-256 hashes detect operator modifications
5. **Modified unit protection:** Requires confirmation to overwrite or remove modified units
6. **Lock-based concurrency:** Prevents concurrent installations
7. **Health checks:** Verifies services start correctly after installation

### Recovery

If service installation fails:

- **Automatic rollback:** All installed files are removed and state is restored
- **Manual recovery:** Check logs with `journalctl -u ainews-web -u ainews-celery-worker -u ainews-celery-beat`
- **State cleanup:** If state becomes inconsistent, remove `~/.config/ainews/service-state.json` and reinstall

### Log Rotation

Configure automatic log rotation for file-backed logs:

```bash
# Install logrotate rule (requires root for system scope)
sudo ainews logrotate configure-rotation

# Validate installed rules
ainews logrotate validate-rotation

# Remove logrotate rules
sudo ainews logrotate remove-rotation
```

**Note:** Log rotation is not needed for journald-managed systemd services or Docker container logs — the container runtime handles rotation for those.

---

## Docker Compose Production Example

The project's `docker-compose.yml` is already production-ready. It includes:

- Multi-stage Dockerfile (builder + runtime)
- Non-root `ainews` user (uid 1000)
- Read-only containers with `tmpfs` for `/tmp`
- Memory limits on all services
- Database migration on startup (`db-migrate` service)
- Redis health checks and volume persistence
- `AINEWS_RUNNING_IN_DOCKER=1` environment variable

To customize for your environment, create a `docker-compose.override.yml`:

```yaml
services:
  web:
    ports:
      - "127.0.0.1:5000:5000"  # Bind to localhost only (use Nginx reverse proxy)
    environment:
      - FLASK_CONFIG=production
      - SECRET_KEY=${SECRET_KEY}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - CELERY_TASK_SECRET=${CELERY_TASK_SECRET}
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
      - DATABASE_URL=${DATABASE_URL:-sqlite:///app/instance/prod.db}

  celery-worker:
    command: celery -A celery_app:celery_app worker -l info --concurrency=4
    deploy:
      resources:
        limits:
          memory: 1G  # Increase for heavy LLM workloads

  celery-beat:
    command: celery -A celery_app:celery_app beat -l info --schedule=/app/instance/celerybeat-schedule
```

Deploy with:
```bash
docker compose up -d
```

---

## Backup and Restore

### Automated Backup Script

The `scripts/backup.sh` script performs the following:
1. Creates WAL checkpoint to ensure consistency
2. Copies the SQLite database file
3. Compresses with gzip
4. Rotates old backups (keeps last 30 days)
5. Creates SHA256 checksum for verification

### Manual Backup

```bash
# Create backup directory
mkdir -p /opt/ainews/backups

# Checkpoint WAL
sqlite3 /opt/ainews/instance/prod.db "PRAGMA wal_checkpoint(TRUNCATE);"

# Copy and compress
cp /opt/ainews/instance/prod.db /opt/ainews/backups/ainews-$(date +%Y%m%d-%H%M%S).db
gzip /opt/ainews/backups/ainews-*.db

# Create checksum
sha256sum /opt/ainews/backups/ainews-*.db.gz > /opt/ainews/backups/checksums.txt
```

### Restore from Backup

```bash
# Stop services
sudo systemctl stop ainews-web ainews-celery-worker ainews-celery-beat

# List available backups
ls -la /opt/ainews/backups/

# Restore (replace date with your backup date)
gunzip -c /opt/ainews/backups/ainews-20240101-020000.db.gz > /opt/ainews/instance/prod.db
sudo chown ainews:ainews /opt/ainews/instance/prod.db

# Verify integrity
sqlite3 /opt/ainews/instance/prod.db "PRAGMA integrity_check;"

# Start services
sudo systemctl start ainews-web ainews-celery-worker ainews-celery-beat
```

### Docker Backup

```bash
# Create backup container
docker compose exec -T web sh -c 'sqlite3 /data/ainews.db "PRAGMA wal_checkpoint(TRUNCATE);"'
docker compose cp web:/data/ainews.db ./backups/ainews-$(date +%Y%m%d-%H%M%S).db
gzip ./backups/ainews-*.db
```

---

## Upgrade and Migration

### Docker Upgrade

```bash
# Pull latest code
git pull origin main

# Rebuild images
docker compose -f docker-compose.prod.yml build

# Restart services (graceful rolling update)
docker compose -f docker-compose.prod.yml up -d --build
```

### Bare Metal Upgrade

```bash
# Pull latest code
cd /opt/ainews
sudo -u ainews git pull origin main

# Activate virtual environment and update dependencies
sudo -u ainews -i
source .venv/bin/activate
uv sync
deactivate

# Restart services
sudo systemctl restart ainews-web ainews-celery-worker ainews-celery-beat
```

### Database Migration

```bash
# Run pending migrations
cd /opt/ainews
source .venv/bin/activate
FLASK_CONFIG=production alembic upgrade head
deactivate
```

### Migration History Note

The migration chain was normalized before public release. A root migration (`000_create_audit_logs`) was added to create tables that existed in models but were missing from the original migration chain (`admin_users`, `audit_logs`, `webhooks`, `webhook_events`, `search_queries`, `quality_reports`). The original `001_initial` migration was rewired to depend on this root. This rewrite is safe because no databases have been deployed yet. If deploying to an existing database created before this normalization, run `flask db upgrade` from the previous head revision before updating.

### Rollback

```bash
# Docker
docker compose -f docker-compose.prod.yml down
git checkout <previous-commit>
docker compose -f docker-compose.prod.yml up -d --build

# Bare metal
sudo systemctl stop ainews-web ainews-celery-worker ainews-celery-beat
sudo -u ainews git checkout <previous-commit>
sudo systemctl start ainews-web ainews-celery-worker ainews-celery-beat
```

---

## Release Checklist

Before tagging a release, verify the following:

1. **All CI checks pass** — lint, tests, smoke tests, Docker build, and Compose boot smoke
2. **Compose boot smoke** runs automatically in CI on every push to `main` and on PRs. Locally, run:
   ```bash
   bash scripts/ci_compose_smoke.sh
   ```
3. **Production config validation** — `ProductionConfig.validate()` rejects missing/weak secrets and invalid providers
4. **Migration smoke** — `flask db upgrade` passes from a fresh database
5. **Ollama healthcheck** — if using the Ollama Compose override, verify `ollama list` works as healthcheck

## Release Validation

Run one command to validate release-equivalent checks locally before pushing or tagging:

```bash
bash scripts/validate_release.sh          # Full validation
bash scripts/validate_release.sh --fast   # Quick: ruff + targeted smoke tests
bash scripts/validate_release.sh --security  # pip-audit + secret scanning
bash scripts/validate_release.sh --with-mypy # Include advisory mypy
```

Or via Make:

```bash
make validate-release          # Full validation
make validate-release-fast     # Quick validation
```

### What each mode runs

| Mode | Steps |
|------|-------|
| `--full` (default) | ruff → pytest → production config smoke → migration smoke → Celery import smoke → docs/env consistency → Docker Compose config → Docker build → Compose smoke |
| `--fast` | ruff → production config smoke → docs/env consistency |
| `--security` | pip-audit → gitleaks (if installed) → trivy (if installed) → license review |

### Environment handling

- Generates throwaway `.env.ci` with random secrets (cleaned up on exit)
- Uses `COMPOSE_PROJECT_NAME=ainews-validation` to isolate from dev deployments
- No real provider API keys required — CI fixture provider config is used where needed
- Prints which environment files are being read

### Prerequisites

- Python 3.12+, `uv`, Docker and Docker Compose (for `--full` mode)
- `gitleaks` and `trivy` are optional (for `--security` mode)

---

## Troubleshooting

### Common Issues

#### Web server won't start

```bash
# Check logs
journalctl -u ainews-web -n 50

# Verify configuration
sudo -u ainews -i
source .venv/bin/activate
python -c "from config import config; print(config['production'].SECRET_KEY)"
deactivate

# Check port availability
ss -tlnp | grep 5000
```

#### Celery workers not processing tasks

```bash
# Check worker status
sudo systemctl status ainews-celery-worker

# View worker logs
journalctl -u ainews-celery-worker -n 50

# Ping workers
sudo -u ainews -i
source .venv/bin/activate
celery -A celery_app inspect ping
deactivate

# Check Redis connectivity
redis-cli ping
```

#### Database locked errors

```bash
# Check for running processes
ps aux | grep -E '(granian|celery|sqlite)'

# Restart services
sudo systemctl restart ainews-web ainews-celery-worker

# If using Docker
docker compose restart web celery-worker
```

#### High memory usage

```bash
# Check memory usage by service
systemctl status ainews-web ainews-celery-worker ainews-celery-beat

# Reduce worker count
sudo systemctl edit ainews-web
# Add: Environment="GRANIAN_WORKERS=3"

# Restart
sudo systemctl restart ainews-web
```

### Performance Tuning

#### Database

```bash
# SQLite WAL mode is automatic; verify
sqlite3 /opt/ainews/instance/prod.db "PRAGMA journal_mode;"

# Vacuum database monthly
sqlite3 /opt/ainews/instance/prod.db "VACUUM;"
```

#### Celery

```bash
# Adjust concurrency based on CPU cores
# Edit /etc/systemd/system/ainews-celery-worker.service
# Change: --concurrency=4 to --concurrency=<2*CPU+1>

# Restart after changes
sudo systemctl daemon-reload
sudo systemctl restart ainews-celery-worker
```

---

## Rate Limiting

### Infrastructure-Level Rate Limiting

Public endpoints (subscribe, article feeds, API) do **not** have per-route rate limiting configured in the application. Instead, rate limiting is handled by the infrastructure layer:

- **WAF (Web Application Firewall)**: For production deployments behind a WAF (Cloudflare, AWS WAF, etc.), configure rate limiting rules there
- **Reverse Proxy (Nginx)**: Rate limiting can be configured in Nginx for production bare-metal deployments

Example Nginx rate limiting configuration:

```nginx
# Rate limit zone - 10 requests per second per IP
limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;

# Apply to public endpoints
location /subscribe {
    limit_req zone=general burst=20 nodelay;
    proxy_pass http://127.0.0.1:5000;
}

location /article {
    limit_req zone=general burst=50 nodelay;
    proxy_pass http://127.0.0.1:5000;
}
```

### Admin Login Lockout

The only application-level rate limiting is for admin login:

- **5 failed attempts** within 15 minutes → **15 minute lockout** per IP
- Implementation: Redis Lua script (atomic, distributed) with in-memory fallback
- Redis key format: `ainews:login_attempts:<ip>`

###Celery Task Rate Limiting

LLM provider slot limiting is handled separately via `services/limiter.py`:
- Per-provider, per-model concurrency limits
- Configurable via provider `concurrency` settings in pipeline.yaml

---

## Lifecycle CLI Commands

The `ainews` CLI provides lifecycle management commands for controlling services:

### Starting Services

```bash
ainews start
ainews start --skip-doctor      # Skip doctor prerequisite checks
ainews start --skip-migrations   # Skip database migrations
ainews start --no-wait          # Start without waiting for health check
ainews start --timeout 180      # Custom timeout (seconds)
ainews start --json             # JSON output
```

### Stopping Services

```bash
ainews stop
```

### Restarting Services

```bash
ainews restart
ainews restart --skip-doctor    # Skip doctor checks before restart
ainews restart --timeout 180    # Custom timeout
```

### Service Status

```bash
ainews status
ainews status --json
```

Displays: Compose service state, health endpoint, Redis, database, Celery workers, pending migrations, and configured providers.

### Viewing Logs

```bash
ainews logs                     # All services
ainews logs web                 # Specific service
ainews logs --tail 200          # More lines
ainews logs --follow            # Follow output
ainews logs --timestamps        # Show timestamps
ainews logs --raw               # Raw passthrough
```

### Health Check

```bash
ainews health
ainews health --timeout 15
ainews health --json
```

### Smoke Tests

```bash
ainews smoke
ainews smoke --timeout 60
ainews smoke --json
```

Runs post-deploy validation: health endpoint, Redis connectivity, Celery workers.

---

## Security

1. **Secrets:** Never commit `.env` to version control. Use `chmod 600 .env`. All production secrets (`SECRET_KEY`, `ADMIN_PASSWORD`, `CELERY_TASK_SECRET`) are validated at startup.
2. **Firewall:** Expose only ports 80/443. Block direct access to port 5000.
3. **SSL:** Always use HTTPS. Use Let's Encrypt for free certificates.
4. **Password:** Use `python scripts/hash_password.py` to generate a hashed admin password. Plaintext passwords are rejected in production.
5. **Redis:** Bind to localhost and disable external access.
6. **Database:** SQLite file should be owned by `ainews` user only.
