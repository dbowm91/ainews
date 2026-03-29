#!/bin/bash
set -euo pipefail

# ainews Deployment Script
# Run as root: sudo bash scripts/deploy.sh [--skip-backup] [--rollback]

APP_DIR="/opt/ainews"
APP_USER="ainews"
SERVICES=("ainews-web" "ainews-celery-worker" "ainews-celery-beat")

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SKIP_BACKUP=false
ROLLBACK=false

for arg in "$@"; do
    case $arg in
        --skip-backup) SKIP_BACKUP=true ;;
        --rollback)    ROLLBACK=true ;;
    esac
done

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root"
    exit 1
fi

# Check if app directory exists
if [[ ! -d "$APP_DIR" ]]; then
    log_error "Application directory $APP_DIR not found"
    exit 1
fi

# Check if virtual environment exists
if [[ ! -d "$APP_DIR/.venv" ]]; then
    log_error "Virtual environment not found at $APP_DIR/.venv"
    log_error "Run install.sh first"
    exit 1
fi

cd "$APP_DIR"

# -------------------------------------------------------
# Rollback mode
# -------------------------------------------------------
if $ROLLBACK; then
    log_info "Rolling back to previous deployment..."

    if [[ ! -f ".last_deploy_commit" ]]; then
        log_error "No previous deployment recorded. Cannot rollback."
        exit 1
    fi

    PREV_COMMIT=$(cat .last_deploy_commit)
    log_info "Rolling back to commit: $PREV_COMMIT"

    sudo -u "$APP_USER" git checkout "$PREV_COMMIT"

    sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r requirements.txt -q

    for service in "${SERVICES[@]}"; do
        if systemctl is-enabled "$service" &>/dev/null; then
            systemctl restart "$service"
        fi
    done

    log_info "Rollback complete. Restarted at commit $PREV_COMMIT"
    exit 0
fi

# -------------------------------------------------------
# 1. Pre-deployment checks
# -------------------------------------------------------
log_info "Running pre-deployment checks..."

# Check git repository
if [[ ! -d ".git" ]]; then
    log_error "Not a git repository"
    exit 1
fi

# Check for uncommitted changes
if [[ -n "$(sudo -u "$APP_USER" git status --porcelain)" ]]; then
    log_warn "Uncommitted changes detected"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deployment cancelled"
        exit 0
    fi
fi

# -------------------------------------------------------
# 2. Record current commit for rollback
# -------------------------------------------------------
CURRENT_COMMIT=$(sudo -u "$APP_USER" git rev-parse --short HEAD)
echo "$CURRENT_COMMIT" > .last_deploy_commit
log_info "Current commit saved for rollback: $CURRENT_COMMIT"

# -------------------------------------------------------
# 3. Pre-deployment backup
# -------------------------------------------------------
if ! $SKIP_BACKUP; then
    if [[ -f "$APP_DIR/scripts/backup.sh" ]]; then
        log_info "Running pre-deployment backup..."
        bash "$APP_DIR/scripts/backup.sh" || log_warn "Backup failed, continuing anyway"
    else
        log_warn "Backup script not found, skipping pre-deploy backup"
    fi
else
    log_info "Skipping pre-deployment backup (--skip-backup)"
fi

# -------------------------------------------------------
# 4. Pull latest code
# -------------------------------------------------------
log_info "Pulling latest code..."
CURRENT_BRANCH=$(sudo -u "$APP_USER" git rev-parse --abbrev-ref HEAD)
log_info "Current branch: $CURRENT_BRANCH"

sudo -u "$APP_USER" git fetch origin
sudo -u "$APP_USER" git pull origin "$CURRENT_BRANCH"

# Get commit info
NEW_COMMIT=$(sudo -u "$APP_USER" git rev-parse --short HEAD)
COMMIT_MSG=$(sudo -u "$APP_USER" git log -1 --pretty=%B | head -1)
log_info "Deploying commit: $NEW_COMMIT - $COMMIT_MSG"

# -------------------------------------------------------
# 5. Install dependencies
# -------------------------------------------------------
log_info "Installing dependencies..."
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip -q
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r requirements.txt -q

# Install granian if not present
if ! sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" show granian &>/dev/null; then
    log_info "Installing granian..."
    sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install granian -q
fi

# -------------------------------------------------------
# 6. Run database migrations
# -------------------------------------------------------
log_info "Running database migrations..."
sudo -u "$APP_USER" env $(grep -v '^#' "$APP_DIR/.env" | xargs) \
    "$APP_DIR/.venv/bin/python" -m flask --app app:create_app db upgrade
log_info "Migrations completed"

# -------------------------------------------------------
# 7. Validate configuration
# -------------------------------------------------------
log_info "Validating configuration..."

if [[ ! -f "$APP_DIR/.env" ]]; then
    log_error ".env file not found"
    exit 1
fi

source "$APP_DIR/.env"
if [[ -z "${SECRET_KEY:-}" ]]; then
    log_error "SECRET_KEY not set in .env"
    exit 1
fi

# -------------------------------------------------------
# 8. Restart services
# -------------------------------------------------------
log_info "Restarting services..."
for service in "${SERVICES[@]}"; do
    if systemctl is-enabled "$service" &>/dev/null; then
        log_info "Restarting $service..."
        systemctl restart "$service"
        sleep 2

        if systemctl is-active "$service" &>/dev/null; then
            log_info "$service is running"
        else
            log_error "$service failed to start"
            journalctl -u "$service" --no-pager -n 20
            log_error "Deploy failed. Rollback with: sudo bash scripts/deploy.sh --rollback"
            exit 1
        fi
    else
        log_warn "$service is not enabled, skipping"
    fi
done

# -------------------------------------------------------
# 9. Post-deployment verification
# -------------------------------------------------------
log_info "Running post-deployment verification..."

sleep 5

# Health check (public endpoint, no auth required)
HEALTH_CHECK_URL="http://127.0.0.1:5000/health"
if command -v curl &>/dev/null; then
    HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_CHECK_URL" || echo "000")
    if [[ "$HEALTH_STATUS" == "200" ]]; then
        log_info "Health check passed (HTTP $HEALTH_STATUS)"
    else
        log_warn "Health check returned HTTP $HEALTH_STATUS"
        log_warn "Application may still be starting up"
    fi
else
    log_warn "curl not found, skipping health check"
fi

# -------------------------------------------------------
# 10. Summary
# -------------------------------------------------------
log_info "============================================="
log_info "Deployment complete!"
log_info "============================================="
log_info ""
log_info "Previous commit: $CURRENT_COMMIT"
log_info "Deployed commit: $NEW_COMMIT"
log_info "Branch: $CURRENT_BRANCH"
log_info ""
log_info "Services restarted:"
for service in "${SERVICES[@]}"; do
    log_info "  - $service"
done
log_info ""
log_info "Rollback:  sudo bash scripts/deploy.sh --rollback"
log_info "Status:    systemctl status ainews-web"
log_info "Logs:      journalctl -u ainews-web -f"
log_info "============================================="
