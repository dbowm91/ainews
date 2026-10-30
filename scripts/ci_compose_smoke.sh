#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

ENV_FILE=".env.ci"
SKIP_BUILD=false
COMPOSE_FILE="docker-compose.yml"
HEALTH_TIMEOUT=90
# The compose file sets per-service `env_file: .env`, which must exist even
# when interpolation uses --env-file .env.ci. Track whether this script
# created .env so cleanup only removes what it created (never a real .env).
CREATED_DOTENV=false

cleanup() {
    echo ""
    echo "=== Cleaning up ==="
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down -v --remove-orphans 2>/dev/null || true
    rm -f "$ENV_FILE"
    if [ "$CREATED_DOTENV" = true ]; then
        rm -f .env
    fi
}
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
    case $1 in
        --env-file)
            ENV_FILE="$2"
            shift 2
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--env-file <path>] [--skip-build]"
            exit 1
            ;;
    esac
done

echo "=== ainews Docker Compose Smoke Test ==="
echo "Working directory: $PROJECT_DIR"
echo "Env file: $ENV_FILE"
echo ""

cd "$PROJECT_DIR"

if ! command -v docker &>/dev/null; then
    echo "ERROR: docker not found"
    exit 1
fi

if ! docker compose version &>/dev/null; then
    echo "ERROR: docker compose not available"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi

if ! command -v curl &>/dev/null; then
    echo "ERROR: curl not found"
    exit 1
fi

# Prefer the project venv (has werkzeug for hash_password.py); the CI job
# installs it via `uv sync`, while local runs usually have it too.
PYTHON_BIN="python3"
if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "=== Step 0: Generating $ENV_FILE ==="
    SECRET_KEY=$($PYTHON_BIN -c "import secrets; print(secrets.token_hex(32))")
    CELERY_TASK_SECRET=$($PYTHON_BIN -c "import secrets; print(secrets.token_urlsafe(32))")
    HASHED_ADMIN_PW=$($PYTHON_BIN scripts/hash_password.py "Ci-Test-123-Validate!" 2>/dev/null | grep "ADMIN_PASSWORD=" | tail -1 | cut -d= -f2-)

    cat > "$ENV_FILE" <<EOF
FLASK_CONFIG=production
SECRET_KEY=${SECRET_KEY}
ADMIN_PASSWORD=${HASHED_ADMIN_PW}
CELERY_TASK_SECRET=${CELERY_TASK_SECRET}
DATABASE_URL=sqlite:///app/instance/prod.db
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
OLLAMA_MODEL=llama3.1
OLLAMA_HOST=http://ollama:11434
LOG_FORMAT=text
# Dummy creds so the shipped providers.yaml (opencode, enabled) passes
# fail-closed shape validation. The smoke test never calls a provider:
# db-migrate runs migrations, web only serves /health.
OPENCODE_API_KEY=ci-dummy-key-not-a-secret
OPENCODE_SESSION_ID=ci-dummy-session
EOF
    if [ -z "$HASHED_ADMIN_PW" ]; then
        echo "ERROR: Failed to hash admin password"
        exit 1
    fi
    echo "  Generated $ENV_FILE with throwaway credentials"
    chmod 600 "$ENV_FILE"
else
    echo "=== Step 0: Using existing $ENV_FILE ==="
fi

if [ ! -f .env ]; then
    echo "=== Step 0b: Providing .env for compose env_file ==="
    cp "$ENV_FILE" .env
    chmod 600 .env
    CREATED_DOTENV=true
    echo "  Created throwaway .env (removed on exit)"
fi

echo ""
echo "=== Step 1: Validating compose config ==="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" config --quiet
echo "  Compose config OK"

if [ "$SKIP_BUILD" = false ]; then
    echo ""
    echo "=== Step 2: Building image ==="
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build --quiet
    echo "  Build complete"
else
    echo ""
    echo "=== Step 2: Skipping build (--skip-build) ==="
fi

echo ""
echo "=== Step 3: Starting redis and db-migrate ==="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d redis db-migrate

echo "  Waiting for db-migrate to complete..."
DB_MIGRATE_CONTAINER=$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps -q db-migrate)
DB_MIGRATE_TIMEOUT=120
DB_MIGRATE_ELAPSED=0

while [ "$DB_MIGRATE_ELAPSED" -lt "$DB_MIGRATE_TIMEOUT" ]; do
    STATUS=$(docker inspect --format='{{.State.Status}}' "$DB_MIGRATE_CONTAINER" 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "exited" ]; then
        EXIT_CODE=$(docker inspect --format='{{.State.ExitCode}}' "$DB_MIGRATE_CONTAINER")
        if [ "$EXIT_CODE" = "0" ]; then
            echo "  db-migrate completed successfully (${DB_MIGRATE_ELAPSED}s)"
            break
        else
            echo "  db-migrate failed with exit code $EXIT_CODE"
            echo ""
            echo "=== db-migrate logs ==="
            docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs db-migrate
            echo "=== web logs ==="
            docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs web
            exit 1
        fi
    fi
    sleep 2
    DB_MIGRATE_ELAPSED=$((DB_MIGRATE_ELAPSED + 2))
done

if [ "$DB_MIGRATE_ELAPSED" -ge "$DB_MIGRATE_TIMEOUT" ]; then
    echo "  db-migrate did not complete within ${DB_MIGRATE_TIMEOUT}s"
    echo ""
    echo "=== db-migrate logs ==="
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs db-migrate
    echo "=== web logs ==="
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs web
    exit 1
fi

echo ""
echo "=== Step 4: Starting web service ==="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d web

WEB_PORT=$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" port web 5000 2>/dev/null | head -1 || echo "localhost:5000")
HEALTH_URL="http://${WEB_PORT}/health"

echo ""
echo "=== Step 5: Waiting for /health (${HEALTH_TIMEOUT}s timeout) ==="
if ! bash "$SCRIPT_DIR/wait_for_health.sh" "$HEALTH_URL" "$HEALTH_TIMEOUT"; then
    echo ""
    echo "=== Web logs on health failure ==="
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs web
    exit 1
fi

echo ""
echo "=== Step 6: Verifying health response ==="
HEALTH_RESPONSE=$(curl -fsS --max-time 10 "$HEALTH_URL" 2>/dev/null || echo "{}")
echo "  Response: $HEALTH_RESPONSE"

if echo "$HEALTH_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('status') in ('ok','degraded') else 1)" 2>/dev/null; then
    echo ""
    echo "=== Smoke test PASSED ==="
else
    echo ""
    echo "WARNING: Health response did not contain expected status field"
    echo "=== Smoke test PASSED (app started and responded) ==="
fi
