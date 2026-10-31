#!/bin/bash
set -euo pipefail

# ainews Development Helper
# Usage: bash scripts/dev.sh [start|stop|status]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/.pids"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_deps() {
    local missing=0

    if ! command -v python3 &>/dev/null; then
        log_error "Python 3 not found"
        missing=1
    fi

    if ! command -v redis-cli &>/dev/null; then
        log_error "Redis not found. Install: brew install redis (macOS) or apt install redis-server (Linux)"
        missing=1
    elif ! redis-cli ping &>/dev/null; then
        log_warn "Redis is not running. Starting it..."
        if command -v brew &>/dev/null; then
            brew services start redis
        elif command -v systemctl &>/dev/null; then
            sudo systemctl start redis-server 2>/dev/null || sudo systemctl start redis 2>/dev/null
        fi
        sleep 1
        if ! redis-cli ping &>/dev/null; then
            log_error "Could not start Redis. Start it manually and retry."
            missing=1
        fi
    fi

    if [ ! -d "$PROJECT_DIR/.venv" ]; then
        log_warn "Virtual environment not found. Creating..."
        python3 -m venv "$PROJECT_DIR/.venv"
        "$PROJECT_DIR/.venv/bin/pip" install uv -q
        "$PROJECT_DIR/.venv/bin/uv" sync --all-extras
        log_info "Virtual environment created and dependencies installed"
    fi

    if [ ! -f "$PROJECT_DIR/.env" ]; then
        log_warn ".env file not found. Copying from .env.example"
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        log_warn "Edit .env to configure your settings before running"
    fi
    chmod 600 "$PROJECT_DIR/.env" 2>/dev/null || true

    return $missing
}

start_services() {
    mkdir -p "$PID_DIR"

    log_info "Starting managed development services..."
    "$PROJECT_DIR/.venv/bin/python" "$SCRIPT_DIR/dev_supervisor.py" start
    sleep 2
    "$PROJECT_DIR/.venv/bin/python" "$SCRIPT_DIR/dev_supervisor.py" status || true
    log_info ""
    log_info "  Flask:      http://localhost:5000"
    log_info "  Admin:      http://localhost:5000/admin/login"
    log_info "  Health:     http://localhost:5000/health"
    log_info ""
    log_info "Logs:  tail -f $PID_DIR/web.log"
    log_info "Stop:  bash scripts/dev.sh stop"
}

stop_services() {
    "$PROJECT_DIR/.venv/bin/python" "$SCRIPT_DIR/dev_supervisor.py" stop
}

show_status() {
    echo ""
    echo -e "${CYAN}Service Status${NC}"
    echo "=============================="

    "$PROJECT_DIR/.venv/bin/python" "$SCRIPT_DIR/dev_supervisor.py" status || true
    echo ""

    # Redis check
    if redis-cli ping &>/dev/null; then
        echo -e "  ${GREEN}running${NC}  redis"
    else
        echo -e "  ${RED}stopped${NC}  redis"
    fi
    echo ""
}

case "${1:-start}" in
    start)
        check_deps
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        sleep 1
        check_deps
        start_services
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: bash scripts/dev.sh [start|stop|restart|status]"
        exit 1
        ;;
esac
