#!/usr/bin/env bash
set -euo pipefail

URL="${1:?Usage: $0 <url> <timeout_seconds>}"
TIMEOUT="${2:-60}"
INTERVAL=2
ELAPSED=0

echo -n "Waiting for $URL ..."

while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
    if curl -fsS --max-time 5 "$URL" > /dev/null 2>&1; then
        echo " ready (${ELAPSED}s)"
        exit 0
    fi
    echo -n "."
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo " timeout after ${TIMEOUT}s"
exit 1
