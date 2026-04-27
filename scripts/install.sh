#!/bin/bash
set -euo pipefail

# ainews Installation Script
# Run as root: sudo bash scripts/install.sh [-d|--dir <path>] [--pull-ollama-model]

APP_NAME="ainews"
APP_USER="ainews"
APP_GROUP="ainews"
APP_DIR="/opt/ainews"
REPO_URL="${REPO_URL:-https://github.com/yourorg/ainews.git}"

# Default flags
PULL_OLLAMA=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--dir)
            APP_DIR="$2"
            shift 2
            ;;
        --pull-ollama-model)
            PULL_OLLAMA=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root"
    exit 1
fi

log_info "Starting ainews installation..."

# -------------------------------------------------------
# 1. Create system user and group
# -------------------------------------------------------
log_info "Creating system user and group..."
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --shell /bin/false --home-dir "$APP_DIR" --create-home "$APP_USER"
    log_info "Created user: $APP_USER"
else
    log_warn "User $APP_USER already exists"
fi

# -------------------------------------------------------
# 2. Install system dependencies
# -------------------------------------------------------
log_info "Installing system dependencies..."
if command -v apt-get &>/dev/null; then
    apt-get update
    apt-get install -y python3.12 python3.12-venv redis-server nginx git
elif command -v dnf &>/dev/null; then
    dnf install -y python3.12 python3.12-venv redis nginx git
elif command -v yum &>/dev/null; then
    yum install -y python3.12 python3.12-venv redis nginx git
else
    log_warn "Unsupported package manager. Please install dependencies manually."
fi

# -------------------------------------------------------
# 3. Enable and start Redis
# -------------------------------------------------------
log_info "Configuring Redis..."
systemctl enable redis-server 2>/dev/null || systemctl enable redis 2>/dev/null || true
systemctl start redis-server 2>/dev/null || systemctl start redis 2>/dev/null || true

# -------------------------------------------------------
# 4. Clone or update repository
# -------------------------------------------------------
log_info "Setting up application directory..."
if [[ -d "$APP_DIR/.git" ]]; then
    log_warn "Repository already exists. Pulling latest changes..."
    cd "$APP_DIR"
    sudo -u "$APP_USER" git pull
else
    if [[ -d "$APP_DIR" ]]; then
        log_warn "Directory $APP_DIR exists but is not a git repo. Backing up..."
        mv "$APP_DIR" "${APP_DIR}.bak.$(date +%Y%m%d%H%M%S)"
    fi
    git clone "$REPO_URL" "$APP_DIR"
    chown -R "$APP_USER":"$APP_GROUP" "$APP_DIR"
fi

# -------------------------------------------------------
# 5. Create Python virtual environment
# -------------------------------------------------------
log_info "Setting up Python virtual environment..."
sudo -u "$APP_USER" python3.12 -m venv "$APP_DIR/.venv"

# -------------------------------------------------------
# 6. Install Python dependencies
# -------------------------------------------------------
log_info "Installing Python dependencies..."
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install granian

# -------------------------------------------------------
# 7. Create directories
# -------------------------------------------------------
log_info "Creating application directories..."
sudo -u "$APP_USER" mkdir -p "$APP_DIR/instance"
sudo -u "$APP_USER" mkdir -p "$APP_DIR/backups"

# -------------------------------------------------------
# 8. Create .env from template
# -------------------------------------------------------
log_info "Configuring environment..."
if [[ ! -f "$APP_DIR/.env" ]]; then
    sudo -u "$APP_USER" cp "$APP_DIR/.env.example" "$APP_DIR/.env"

    # Generate SECRET_KEY
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" "$APP_DIR/.env"

    # Generate and hash admin password
    ADMIN_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
    ADMIN_PASS_HASHED=$(sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/hash_password.py" "$ADMIN_PASS" 2>/dev/null | grep "ADMIN_PASSWORD=" | cut -d= -f2-)
    if [[ -n "$ADMIN_PASS_HASHED" ]]; then
        sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$ADMIN_PASS_HASHED|" "$APP_DIR/.env"
        log_info "Admin password hashed with scrypt"
    else
        # Fallback if hashing script fails
        sed -i "s/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$ADMIN_PASS/" "$APP_DIR/.env"
        log_warn "Could not hash password — stored as plaintext. Run 'python scripts/hash_password.py' to generate a hash."
    fi

    chmod 600 "$APP_DIR/.env"
    chown "$APP_USER":"$APP_GROUP" "$APP_DIR/.env"

    log_warn "Generated .env file with random credentials."
    log_warn "Admin password: $ADMIN_PASS"
    log_warn "Please edit $APP_DIR/.env to configure SMTP, LLM providers, etc."
else
    log_warn ".env file already exists. Skipping creation."
fi

# -------------------------------------------------------
# 9. Verify config files
# -------------------------------------------------------
log_info "Checking configuration files..."

if [[ ! -f "$APP_DIR/providers.yaml" ]]; then
    log_warn "providers.yaml not found — LLM providers will not be available"
    log_warn "Create providers.yaml to configure Ollama, OpenAI, or Anthropic"
fi

if [[ ! -f "$APP_DIR/sources.yaml" ]]; then
    log_warn "sources.yaml not found — no RSS sources configured"
fi

# -------------------------------------------------------
# 10. Pull Ollama model (optional)
# -------------------------------------------------------
if command -v ollama &>/dev/null; then
    OLLAMA_MODEL=$(grep "^OLLAMA_MODEL=" "$APP_DIR/.env" 2>/dev/null | cut -d= -f2- || echo "")
    if [[ -n "$OLLAMA_MODEL" && "$OLLAMA_MODEL" != "llama3.1" ]]; then
        log_info "Ollama detected. Pull model '$OLLAMA_MODEL'?"
        if [[ $PULL_OLLAMA == true ]] || (read -p "  Pull model now? (y/N) " -n 1 -r && echo && [[ $REPLY =~ ^[Yy]$ ]]); then
            ollama pull "$OLLAMA_MODEL"
            log_info "Model $OLLAMA_MODEL pulled"
        else
            log_warn "Skipping model pull. Run 'ollama pull $OLLAMA_MODEL' later."
        fi
    fi
else
    log_info "Ollama not detected. Install from https://ollama.ai for local LLM inference."
fi

# -------------------------------------------------------
# 11. Initialize database
# -------------------------------------------------------
log_info "Initializing database..."
sudo -u "$APP_USER" env $(grep -v '^#' "$APP_DIR/.env" | xargs) \
    "$APP_DIR/.venv/bin/python" -c "from app import create_app; app = create_app(); app.app_context().__enter__()"
log_info "Database initialized at $APP_DIR/instance/ainews.db"

# -------------------------------------------------------
# 12. Install systemd services
# -------------------------------------------------------
log_info "Installing systemd services..."
cp "$APP_DIR/systemd/ainews-web.service" /etc/systemd/system/
cp "$APP_DIR/systemd/ainews-celery-worker.service" /etc/systemd/system/
cp "$APP_DIR/systemd/ainews-celery-beat.service" /etc/systemd/system/

systemctl daemon-reload

# -------------------------------------------------------
# 13. Enable and start services
# -------------------------------------------------------
log_info "Enabling and starting services..."
systemctl enable ainews-web ainews-celery-worker ainews-celery-beat
systemctl start ainews-web ainews-celery-worker ainews-celery-beat

# -------------------------------------------------------
# 14. Configure Nginx
# -------------------------------------------------------
log_info "Nginx configuration..."
log_warn "Nginx config not bundled. See docs/deployment.md for Nginx reverse proxy setup."

# -------------------------------------------------------
# Summary
# -------------------------------------------------------
log_info "============================================="
log_info "Installation complete!"
log_info "============================================="
log_info ""
log_info "Application: $APP_DIR"
log_info "Services:"
log_info "  - ainews-web"
log_info "  - ainews-celery-worker"
log_info "  - ainews-celery-beat"
log_info ""
log_info "Check service status:"
log_info "  systemctl status ainews-web"
log_info ""
log_info "View logs:"
log_info "  journalctl -u ainews-web -f"
log_info ""
log_info "Install options used:"
log_info "  -d, --dir <path>         : Override app directory (default: /opt/ainews)"
log_info "  --pull-ollama-model     : Auto-pull Ollama model without prompting"
log_info "  REPO_URL=<url>          : Override repo URL via environment variable"
log_info ""
log_info "IMPORTANT: Edit $APP_DIR/.env to configure:"
log_info "  - SMTP settings for newsletter delivery"
log_info "  - LLM provider (Ollama/OpenAI/Anthropic)"
log_info ""
log_info "============================================="
