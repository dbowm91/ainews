#!/bin/bash
set -euo pipefail

# ainews Test Runner
# Usage: bash scripts/test.sh [options]
# Options:
#   --cov        Run with coverage report
#   --verbose    Verbose output
#   --pattern    Filter tests by pattern (e.g., "test_routes")

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

COVERAGE=false
VERBOSE=""
PATTERN=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --cov)    COVERAGE=true; shift ;;
        --verbose) VERBOSE="-v"; shift ;;
        --pattern) PATTERN="$2"; shift 2 ;;
        *)        shift ;;
    esac
done

cd "$PROJECT_DIR"

if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Run: bash scripts/dev.sh"
    exit 1
fi

source .venv/bin/activate

# Ensure dev dependencies are installed
.venv/bin/pip install uv -q 2>/dev/null
.venv/bin/uv sync --all-extras 2>/dev/null

echo "Running tests..."
echo "===================="

if $COVERAGE; then
    if [ -n "$PATTERN" ]; then
        python -m pytest tests/ -k "$PATTERN" $VERBOSE --cov=. --cov-report=term-missing --cov-report=html:htmlcov
    else
        python -m pytest tests/ $VERBOSE --cov=. --cov-report=term-missing --cov-report=html:htmlcov
    fi
    echo ""
    echo "Coverage report: htmlcov/index.html"
else
    if [ -n "$PATTERN" ]; then
        python -m pytest tests/ -k "$PATTERN" $VERBOSE
    else
        python -m pytest tests/ $VERBOSE
    fi
fi
