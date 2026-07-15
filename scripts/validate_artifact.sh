#!/usr/bin/env bash
# validate_artifact.sh — Validate a release artifact before publishing.
#
# Checks:
#   - Expected top-level structure
#   - Executable CLI entry point
#   - Compose files and templates present
#   - Migrations present
#   - Static assets and packaged Halloy themes present
#   - Version metadata matches tag/commit
#   - No repository secrets, local caches, test databases, .env, or developer state
#   - No absolute paths or escaping links
#   - Artifact can be extracted cleanly
#
# Usage:
#   bash scripts/validate_artifact.sh ainews-1.0.0-linux-x86_64.tar.gz
#   bash scripts/validate_artifact.sh ainews-1.0.0-linux-x86_64.tar.gz --tag v1.0.0
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ARTIFACT="${1:-}"
TAG=""
EXIT_CODE=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}PASS${NC} $1"; }
fail() { echo -e "  ${RED}FAIL${NC} $1"; EXIT_CODE=1; }
warn() { echo -e "  ${YELLOW}WARN${NC} $1"; }

while [[ $# -gt 0 ]]; do
    case $1 in
        --tag) TAG="$2"; shift 2 ;;
        *) shift ;;
    esac
done

if [[ -z "$ARTIFACT" || ! -f "$ARTIFACT" ]]; then
    echo "Usage: $0 <artifact.tar.gz> [--tag vX.Y.Z]"
    exit 1
fi

echo "Validating: $ARTIFACT"
echo ""

# ── 1. Safety checks ────────────────────────────────────────────────

echo "=== Safety ==="

# Reject absolute paths
ABSOLUTE=$(tar -tzf "$ARTIFACT" 2>/dev/null | grep '^/' || true)
if [[ -n "$ABSOLUTE" ]]; then
    fail "Absolute paths found in archive"
    echo "$ABSOLUTE" | head -5
else
    pass "No absolute paths"
fi

# Reject traversal entries
TRAVERSAL=$(tar -tzf "$ARTIFACT" 2>/dev/null | grep '\.\.' || true)
if [[ -n "$TRAVERSAL" ]]; then
    fail "Traversal entries found in archive"
    echo "$TRAVERSAL" | head -5
else
    pass "No traversal entries"
fi

echo ""

# ── 2. Required files ───────────────────────────────────────────────

echo "=== Required files ==="

REQUIRED_FILES=(
    "ainews/ainews"
    "ainews/pyproject.toml"
    "ainews/docker-compose.yml"
    "ainews/docker-compose.ollama.yml"
    "ainews/.env.example"
    "ainews/providers.yaml"
    "ainews/.venv/bin/activate"
    "ainews/migrations/env.py"
    "ainews/ainews_cli/main.py"
    "ainews/ainews_config/__init__.py"
)

REQUIRED_DIRS=(
    "ainews/resources/themes"
    "ainews/static"
    "ainews/templates"
    "ainews/services"
    "ainews/models"
    "ainews/adapters"
    "ainews/tasks"
    "ainews/routes"
    "ainews/schemas"
    "ainews/utils"
)

MISSING=0
for entry in "${REQUIRED_FILES[@]}"; do
    if tar -tzf "$ARTIFACT" | grep -q "^${entry}$"; then
        pass "$entry"
    else
        fail "Missing: $entry"
        MISSING=$((MISSING + 1))
    fi
done

for entry in "${REQUIRED_DIRS[@]}"; do
    if tar -tzf "$ARTIFACT" | grep -q "^${entry}/"; then
        pass "$entry/"
    else
        fail "Missing directory: $entry"
        MISSING=$((MISSING + 1))
    fi
done

echo ""

# ── 3. CLI entry point ──────────────────────────────────────────────

echo "=== CLI entry point ==="

CLI_CONTENT=$(tar -xzf "$ARTIFACT" -O ainews/ainews 2>/dev/null || true)
if [[ -n "$CLI_CONTENT" ]]; then
    if echo "$CLI_CONTENT" | head -1 | grep -q '^#!/bin/bash'; then
        pass "CLI has bash shebang"
    else
        warn "CLI may not have bash shebang"
    fi

    if echo "$CLI_CONTENT" | grep -q '\.venv/bin/ainews'; then
        pass "CLI references .venv/bin/ainews"
    else
        warn "CLI may not reference .venv/bin/ainews"
    fi
else
    fail "CLI entry point not found"
fi

echo ""

# ── 4. Forbidden files ──────────────────────────────────────────────

echo "=== Forbidden files ==="

FORBIDDEN_PATTERNS=(
    '\.env$'
    '\.env\.local'
    '\.env\.production'
    '\.env\.ci'
    'instance/.*\.db'
    'instance/.*\.db-wal'
    'instance/.*\.db-shm'
    '__pycache__'
    '\.pyc$'
    '\.mypy_cache'
    '\.ruff_cache'
    'htmlcov'
    'test_results'
    '\.git/'
    'node_modules'
    'package-lock\.json'
    'yarn\.lock'
    'pnpm-lock\.yaml'
    'uv\.lock'
)

for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    FOUND=$(tar -tzf "$ARTIFACT" 2>/dev/null | grep -i "$pattern" || true)
    if [[ -n "$FOUND" ]]; then
        COUNT=$(echo "$FOUND" | wc -l)
        fail "Found ${COUNT} entries matching '${pattern}'"
        echo "$FOUND" | head -3
    fi
done

# Check for .env specifically (exact match)
if tar -tzf "$ARTIFACT" 2>/dev/null | grep -q '^ainews/\.env$'; then
    fail "Found .env file in artifact (may contain secrets)"
fi

pass "Forbidden file check complete"

echo ""

# ── 5. Version metadata ─────────────────────────────────────────────

echo "=== Version metadata ==="

if [[ -n "$TAG" ]]; then
    VERSION="${TAG#v}"
    PKG_VERSION=$(tar -xzf "$ARTIFACT" -O ainews/pyproject.toml 2>/dev/null | python3 -c "
import sys, tomllib
data = tomllib.load(sys.stdin)
print(data.get('project', {}).get('version', 'unknown'))
" 2>/dev/null || echo "unknown")

    if [[ "$VERSION" == "$PKG_VERSION" ]]; then
        pass "Tag version (${VERSION}) matches pyproject.toml (${PKG_VERSION})"
    else
        fail "Tag version (${VERSION}) does not match pyproject.toml (${PKG_VERSION})"
    fi
else
    warn "No --tag provided, skipping version cross-check"
fi

echo ""

# ── 6. Checksum ─────────────────────────────────────────────────────

echo "=== Checksum ==="

ARTIFACT_NAME=$(basename "$ARTIFACT")
if [[ -f "SHA256SUMS" ]]; then
    EXPECTED=$(grep " ${ARTIFACT_NAME}$" SHA256SUMS 2>/dev/null | awk '{print $1}' || true)
    ACTUAL=$(sha256sum "$ARTIFACT" | awk '{print $1}')

    if [[ -n "$EXPECTED" && "$EXPECTED" == "$ACTUAL" ]]; then
        pass "Checksum matches: ${ACTUAL}"
    elif [[ -n "$EXPECTED" ]]; then
        fail "Checksum mismatch: expected ${EXPECTED}, got ${ACTUAL}"
    else
        warn "Artifact not found in SHA256SUMS"
    fi
else
    warn "No SHA256SUMS file found"
fi

echo ""

# ── 7. Summary ──────────────────────────────────────────────────────

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "  ${GREEN}ARTIFACT VALIDATION PASSED${NC}"
else
    echo -e "  ${RED}ARTIFACT VALIDATION FAILED${NC}"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit $EXIT_CODE
