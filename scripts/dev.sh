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
        "$PROJECT_DIR/.venv/bin/pip" install --upgrade pip -q
        "$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt" -q
        "$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements-dev.txt" -q
        log_info "Virtual environment created and dependencies installed"
    fi

    if [ ! -f "$PROJECT_DIR/.env" ]; then
        log_warn ".env file not found. Copying from .env.example"
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        log_warn "Edit .env to configure your settings before running"
    fi

    return $missing
}

start_services() {
    mkdir -p "$PID_DIR"

    log_info "Starting development services..."

    # Flask
    log_info "Starting Flask dev server on http://localhost:5000"
    (
        cd "$PROJECT_DIR"
        source .venv/bin/activate
        flask run --reload --port 5000
    ) > "$PID_DIR/flask.log" 2>&1 &
    echo $! > "$PID_DIR/flask.pid"
    log_info "  Flask PID: $(cat "$PID_DIR/flask.pid")"

    # Celery Worker
    log_info "Starting Celery worker"
    (
        cd "$PROJECT_DIR"
        source .venv/bin/activate
        celery -A celery_app:celery_app worker -l info --concurrency=2
    ) > "$PID_DIR/celery-worker.log" 2>&1 &
    echo $! > "$PID_DIR/celery-worker.pid"
    log_info "  Celery worker PID: $(cat "$PID_DIR/celery-worker.pid")"

    # Celery Beat
    log_info "Starting Celery beat scheduler"
    (
        cd "$PROJECT_DIR"
        source .venv/bin/activate
        celery -A celery_app:celery_app beat -l info --schedule="$PID_DIR/celerybeat-schedule"
    ) > "$PID_DIR/celery-beat.log" 2>&1 &
    echo $! > "$PID_DIR/celery-beat.pid"
    log_info "  Celery beat PID: $(cat "$PID_DIR/celery-beat.pid")"

    sleep 2
    log_info ""
    log_info "All services started"
    log_info ""
    log_info "  Flask:      http://localhost:5000"
    log_info "  Admin:      http://localhost:5000/admin/login"
    log_info "  Health:     http://localhost:5000/health"
    log_info ""
    log_info "Logs:  tail -f $PID_DIR/flask.log"
    log_info "Stop:  bash scripts/dev.sh stop"
}

stop_services() {
    log_info "Stopping development services..."

    for svc in flask celery-worker celery-beat; do
        pidfile="$PID_DIR/$svc.pid"
        if [ -f "$pidfile" ]; then
            pid=$(cat "$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid" 2>/dev/null
                log_info "Stopped $svc (PID $pid)"
            fi
            rm -f "$pidfile"
        fi
    done

    # Clean up any leftover celery processes
    pkill -f "celery -A celery_app" 2>/dev/null || true

    log_info "All services stopped"
}

show_status() {
    echo ""
    echo -e "${CYAN}Service Status${NC}"
    echo "=============================="

    for svc in flask celery-worker celery-beat; do
        pidfile="$PID_DIR/$svc.pid"
        if [ -f "$pidfile" ]; then
            pid=$(cat "$pidfile")
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "  ${GREEN}running${NC}  $svc (PID $pid)"
            else
                echo -e "  ${RED}stopped${NC}  $svc (stale pidfile)"
            fi
        else
            echo -e "  ${YELLOW}stopped${NC}  $svc"
        fi
    done
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
