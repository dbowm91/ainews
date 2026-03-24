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

    # Static files — serve directly
    location /static/ {
        proxy_pass http://127.0.0.1:5000/static/;
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

## Security

1. **Secrets:** Never commit `.env` to version control. Use `chmod 600 .env`.
2. **Firewall:** Expose only ports 80/443. Block direct access to port 5000.
3. **SSL:** Always use HTTPS. Use Let's Encrypt for free certificates.
4. **Password:** Use `python scripts/hash_password.py` to generate a hashed admin password.
5. **Redis:** Bind to localhost and disable external access.
6. **Database:** SQLite file should be owned by `ainews` user only.
