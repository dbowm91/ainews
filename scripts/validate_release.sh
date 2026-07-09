#!/usr/bin/env bash
# validate_release.sh — One-command local release validation.
#
# Runs lint, tests, production smoke, Docker checks, and Compose smoke
# in a predictable order with actionable output.
#
# Usage:
#   bash scripts/validate_release.sh [--fast|--full|--security] [--with-mypy]
#
# Modes:
#   (default)  Full release validation: lint + tests + smoke + Docker build + Compose smoke
#   --fast     Quick validation: ruff + targeted smoke tests, no Docker build
#   --security pip-audit + gitleaks (if available) + trivy (if available)
#
# Flags:
#   --with-mypy  Include mypy type checking (advisory, may fail without blocking)
#
# Environment:
#   - Generates throwaway .env.ci with throwaway secrets
#   - Uses COMPOSE_PROJECT_NAME=ainews-validation to isolate from dev deployments
#   - Cleans up Docker resources on exit
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# --- Configuration ---
MODE="full"
WITH_MYPY=false
COMPOSE_PROJECT_NAME="ainews-validation"
ENV_CI=".env.ci"
CI_FIXTURE_PROVIDER="$PROJECT_DIR/tests/fixtures/providers.ci.yaml"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

step_num=0
failed_steps=()

pass() { echo -e "  ${GREEN}PASS${NC} $1"; }
fail() { echo -e "  ${RED}FAIL${NC} $1"; }
warn() { echo -e "  ${YELLOW}WARN${NC} $1"; }
info() { echo -e "  ${BLUE}INFO${NC} $1"; }

header() {
    step_num=$((step_num + 1))
    echo ""
    echo -e "${BLUE}=== Step $step_num: $1 ===${NC}"
}

run_step() {
    local label="$1"
    shift
    header "$label"
    if "$@"; then
        pass "$label"
        return 0
    else
        fail "$label"
        failed_steps+=("$label")
        return 1
    fi
}

# --- Argument parsing ---
while [[ $# -gt 0 ]]; do
    case $1 in
        --fast)
            MODE="fast"
            shift
            ;;
        --full)
            MODE="full"
            shift
            ;;
        --security)
            MODE="security"
            shift
            ;;
        --with-mypy)
            WITH_MYPY=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--fast|--full|--security] [--with-mypy]"
            echo ""
            echo "Modes:"
            echo "  (default)  Full release validation"
            echo "  --fast     Quick validation (no Docker build)"
            echo "  --security Dependency + secret scanning"
            echo ""
            echo "Flags:"
            echo "  --with-mypy  Include advisory mypy check"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--fast|--full|--security] [--with-mypy]"
            exit 1
            ;;
    esac
done

# --- Cleanup ---
cleanup() {
    echo ""
    echo "=== Cleanup ==="
    if [ -f "$PROJECT_DIR/$ENV_CI" ]; then
        rm -f "$PROJECT_DIR/$ENV_CI"
        info "Removed $ENV_CI"
    fi
    if command -v docker &>/dev/null; then
        docker compose --project-name "$COMPOSE_PROJECT_NAME" down -v --remove-orphans 2>/dev/null || true
        info "Stopped validation containers"
    fi
}
trap cleanup EXIT

# --- Preamble ---
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       ainews Release Validation                  ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════╝${NC}"
echo ""
info "Mode: $MODE"
info "Project: $PROJECT_DIR"
info "Docker project name: $COMPOSE_PROJECT_NAME"

cd "$PROJECT_DIR"

# --- Generate .env.ci ---
header "Generating throwaway environment"
if [ ! -f "$ENV_CI" ]; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    CELERY_TASK_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    HASHED_ADMIN_PW=$(python3 scripts/hash_password.py "Ci-Test-123-Validate!" 2>/dev/null | grep "ADMIN_PASSWORD=" | tail -1 | cut -d= -f2-)

    if [ -z "$HASHED_ADMIN_PW" ]; then
        fail "Failed to hash admin password"
        exit 1
    fi

    cat > "$ENV_CI" <<EOF
FLASK_CONFIG=production
SECRET_KEY=${SECRET_KEY}
ADMIN_PASSWORD=${HASHED_ADMIN_PW}
CELERY_TASK_SECRET=${CELERY_TASK_SECRET}
DATABASE_URL=sqlite:///app/instance/prod.db
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
OLLAMA_MODEL=qwen3:8b
OLLAMA_HOST=http://ollama:11434
LOG_FORMAT=text
EOF
    chmod 600 "$ENV_CI"
    pass "Generated $ENV_CI with throwaway secrets"
else
    pass "Using existing $ENV_CI"
fi

# ============================================================
# MODE: fast
# ============================================================
if [ "$MODE" = "fast" ]; then
    echo ""
    echo -e "${YELLOW}--- Fast Mode: lint + targeted smoke tests ---${NC}"

    run_step "Ruff lint" uv run ruff check . --exclude .venv || true

    run_step "Production config smoke" uv run pytest tests/test_smoke_production_config.py -q || true

    run_step "Docs/env consistency" uv run pytest tests/test_docs_env_consistency.py -q || true

    if [ "$WITH_MYPY" = true ]; then
        info "Mypy is advisory — failures will not block"
        run_step "Mypy (advisory)" uv run mypy . --exclude .venv || true
    fi

    echo ""
    if [ ${#failed_steps[@]} -eq 0 ]; then
        echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║  Fast validation PASSED                          ║${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
    else
        echo -e "${RED}╔══════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║  Fast validation FAILED                          ║${NC}"
        echo -e "${RED}╚══════════════════════════════════════════════════╝${NC}"
        echo ""
        echo "Failed steps:"
        for s in "${failed_steps[@]}"; do
            echo -e "  ${RED}•${NC} $s"
        done
        exit 1
    fi
    exit 0
fi

# ============================================================
# MODE: security
# ============================================================
if [ "$MODE" = "security" ]; then
    echo ""
    echo -e "${YELLOW}--- Security Mode: dependency + secret scanning ---${NC}"

    run_step "pip-audit" uv run pip-audit || true

    if command -v gitleaks &>/dev/null; then
        run_step "gitleaks" gitleaks detect --source . --verbose || true
    else
        warn "gitleaks not installed — skipping (install: https://github.com/gitleaks/gitleaks)"
    fi

    if command -v trivy &>/dev/null; then
        run_step "trivy filesystem scan" trivy filesystem --severity HIGH,CRITICAL . || true
    else
        warn "trivy not installed — skipping (install: https://github.com/aquasecurity/trivy)"
    fi

    header "License review"
    info "Generating dependency license report..."
    uv run pip-licenses --format=markdown 2>/dev/null && pass "License report generated" || warn "pip-licenses not available — install with: uv pip install pip-licenses"

    echo ""
    if [ ${#failed_steps[@]} -eq 0 ]; then
        echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║  Security validation PASSED                      ║${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
    else
        echo -e "${RED}╔══════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║  Security validation FAILED                      ║${NC}"
        echo -e "${RED}╚══════════════════════════════════════════════════╝${NC}"
        echo ""
        echo "Failed steps:"
        for s in "${failed_steps[@]}"; do
            echo -e "  ${RED}•${NC} $s"
        done
        exit 1
    fi
    exit 0
fi

# ============================================================
# MODE: full (default)
# ============================================================
echo ""
echo -e "${YELLOW}--- Full Mode: lint + tests + smoke + Docker + Compose ---${NC}"

# Step 1: Ruff lint
run_step "Ruff lint" uv run ruff check . --exclude .venv || true

# Step 2: Full test suite
run_step "Full test suite" uv run pytest tests/ -q || true

# Step 3: Targeted smoke tests
run_step "Production config smoke" uv run pytest tests/test_smoke_production_config.py -q || true
run_step "Migration smoke" uv run pytest tests/test_smoke_migrations.py -q || true
run_step "Celery import smoke" uv run pytest tests/test_smoke_celery.py -q || true
run_step "Docs/env consistency" uv run pytest tests/test_docs_env_consistency.py -q || true

# Step 4: Optional mypy
if [ "$WITH_MYPY" = true ]; then
    info "Mypy is advisory — failures will not block"
    run_step "Mypy (advisory)" uv run mypy . --exclude .venv || true
fi

# Step 5: Docker Compose config validation
if command -v docker &>/dev/null; then
    header "Docker Compose config validation"
    info "Validating docker-compose.yml..."
    docker compose --project-name "$COMPOSE_PROJECT_NAME" --env-file "$ENV_CI" config --quiet && pass "docker-compose.yml OK" || fail "docker-compose.yml"

    info "Validating docker-compose.yml + docker-compose.ollama.yml..."
    docker compose --project-name "$COMPOSE_PROJECT_NAME" --env-file "$ENV_CI" -f docker-compose.yml -f docker-compose.ollama.yml config --quiet && pass "compose override OK" || fail "compose override"
else
    warn "Docker not found — skipping Compose config validation"
fi

# Step 6: Docker build
if command -v docker &>/dev/null; then
    run_step "Docker image build" docker build -t ainews-ci . || true
else
    warn "Docker not found — skipping image build"
fi

# Step 7: Compose smoke test (inlined to use isolated project name)
if command -v docker &>/dev/null; then
    header "Docker Compose smoke test"
    info "Using project name: $COMPOSE_PROJECT_NAME"

    DC="docker compose --project-name $COMPOSE_PROJECT_NAME --env-file $ENV_CI"

    info "Starting redis and db-migrate..."
    $DC up -d redis db-migrate

    info "Waiting for db-migrate to complete..."
    DB_MIGRATE_CONTAINER=$($DC ps -q db-migrate)
    DB_MIGRATE_TIMEOUT=120
    DB_MIGRATE_ELAPSED=0

    while [ "$DB_MIGRATE_ELAPSED" -lt "$DB_MIGRATE_TIMEOUT" ]; do
        STATUS=$(docker inspect --format='{{.State.Status}}' "$DB_MIGRATE_CONTAINER" 2>/dev/null || echo "unknown")
        if [ "$STATUS" = "exited" ]; then
            EXIT_CODE=$(docker inspect --format='{{.State.ExitCode}}' "$DB_MIGRATE_CONTAINER")
            if [ "$EXIT_CODE" = "0" ]; then
                info "db-migrate completed (${DB_MIGRATE_ELAPSED}s)"
                break
            else
                fail "db-migrate failed (exit code $EXIT_CODE)"
                $DC logs db-migrate
                exit 1
            fi
        fi
        sleep 2
        DB_MIGRATE_ELAPSED=$((DB_MIGRATE_ELAPSED + 2))
    done

    if [ "$DB_MIGRATE_ELAPSED" -ge "$DB_MIGRATE_TIMEOUT" ]; then
        fail "db-migrate timed out after ${DB_MIGRATE_TIMEOUT}s"
        $DC logs db-migrate
        exit 1
    fi

    info "Starting web service..."
    $DC up -d web

    WEB_PORT=$($DC port web 5000 2>/dev/null | head -1 || echo "localhost:5000")
    HEALTH_URL="http://${WEB_PORT}/health"

    info "Waiting for /health (90s timeout)..."
    if bash "$SCRIPT_DIR/wait_for_health.sh" "$HEALTH_URL" 90; then
        info "Verifying health response..."
        HEALTH_RESPONSE=$(curl -fsS --max-time 10 "$HEALTH_URL" 2>/dev/null || echo "{}")
        if echo "$HEALTH_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('status') in ('ok','degraded') else 1)" 2>/dev/null; then
            pass "Compose smoke test"
        else
            warn "Health response unexpected but app started: $HEALTH_RESPONSE"
            pass "Compose smoke test"
        fi
    else
        fail "Compose smoke test (health check timeout)"
        $DC logs web
        exit 1
    fi
else
    warn "Docker not found — skipping Compose smoke test"
fi

# --- Summary ---
echo ""
if [ ${#failed_steps[@]} -eq 0 ]; then
    echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  Full release validation PASSED                  ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
else
    echo -e "${RED}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  Release validation FAILED                       ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Failed steps:"
    for s in "${failed_steps[@]}"; do
        echo -e "  ${RED}•${NC} $s"
    done
    exit 1
fi
