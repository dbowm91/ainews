# Production Deployment Guide

Deploy ainews to a production server using Docker (recommended) or bare metal with systemd.

## Option A: Docker (Recommended)

### Prerequisites

- Docker and Docker Compose
- A `.env` file with production settings

### Quick Deploy

```bash
git clone https://github.com/yourorg/ainews.git
cd ainews
cp .env.example .env
```

Edit `.env`:
```bash
FLASK_CONFIG=production
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
ADMIN_PASSWORD=<run: python scripts/hash_password.py>
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
```

Start:
```bash
docker compose up -d
```

Verify:
```bash
docker compose ps
curl http://localhost:5000/health
```

### Docker Services

| Service | Description |
|---------|-------------|
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
git clone https://github.com/yourorg/ainews.git .
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install granian
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
| `ainews-web` | Granian WSGI server | 1 GB |
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

# Admin (requires auth)
curl -u admin:password http://localhost:5000/admin/api/health
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
ExecStart=/opt/ainews/.venv/bin/granian --host 127.0.0.1 --port 5000 --workers 5 --threading --interface wsgi app:app
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

---

## Docker Compose Production Example

Create `docker-compose.prod.yml`:

```yaml
version: "3.8"

services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
    restart: always
    environment:
      - FLASK_CONFIG=production
      - SECRET_KEY=${SECRET_KEY}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
      - DATABASE_URL=sqlite:////data/ainews.db
      - REDIS_URL=redis://redis:6379/2
    volumes:
      - ./data:/data
      - ./instance:/opt/ainews/instance
    ports:
      - "127.0.0.1:5000:5000"
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  celery-worker:
    build:
      context: .
      dockerfile: Dockerfile
    restart: always
    command: celery -A celery_app worker --loglevel=info --concurrency=4
    environment:
      - FLASK_CONFIG=production
      - SECRET_KEY=${SECRET_KEY}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
      - DATABASE_URL=sqlite:////data/ainews.db
      - REDIS_URL=redis://redis:6379/2
    volumes:
      - ./data:/data
      - ./instance:/opt/ainews/instance
    depends_on:
      - redis
    deploy:
      resources:
        limits:
          memory: 2G

  celery-beat:
    build:
      context: .
      dockerfile: Dockerfile
    restart: always
    command: celery -A celery_app beat --loglevel=info
    environment:
      - FLASK_CONFIG=production
      - SECRET_KEY=${SECRET_KEY}
      - ADMIN_PASSWORD=${ADMIN_PASSWORD}
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/1
      - DATABASE_URL=sqlite:////data/ainews.db
      - REDIS_URL=redis://redis:6379/2
    volumes:
      - ./data:/data
      - ./instance:/opt/ainews/instance
    depends_on:
      - redis
    deploy:
      resources:
        limits:
          memory: 512M

  redis:
    image: redis:7-alpine
    restart: always
    ports:
      - "127.0.0.1:6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru

volumes:
  redis_data:
  data:

networks:
  default:
    name: anews_network
```

Deploy with:
```bash
docker compose -f docker-compose.prod.yml up -d
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
pip install -r requirements.txt
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

## Security

1. **Secrets:** Never commit `.env` to version control. Use `chmod 600 .env`.
2. **Firewall:** Expose only ports 80/443. Block direct access to port 5000.
3. **SSL:** Always use HTTPS. Use Let's Encrypt for free certificates.
4. **Password:** Use `python scripts/hash_password.py` to generate a hashed admin password.
5. **Redis:** Bind to localhost and disable external access.
6. **Database:** SQLite file should be owned by `ainews` user only.
