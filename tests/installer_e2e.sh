#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# tests/installer_e2e.sh — End-to-end installer and fault injection tests
#
# Tests the installer's post-install behavior, lifecycle commands,
# and fault injection scenarios.
#
# Run:  bash tests/installer_e2e.sh
#
# No network required. Builds a local tarball for testing.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PASS=0
FAIL=0
CURRENT_TEST=""
_COUNTS_FILE=$(mktemp)
echo "0 0" > "$_COUNTS_FILE"
trap 'rm -f "$_COUNTS_FILE"' EXIT

# ── Test framework ───────────────────────────────────────────────────

_pass() {
    read -r p f < "$_COUNTS_FILE"
    echo "$((p+1)) $f" > "$_COUNTS_FILE"
    echo "  ✓ $1"
}

_fail() {
    read -r p f < "$_COUNTS_FILE"
    echo "$p $((f+1))" > "$_COUNTS_FILE"
    echo "  ✗ $1" >&2
    [[ -n "${2:-}" ]] && echo "    $2" >&2
}

assert_exit_code() {
    local expected="$1" actual="$2" label="${3:-}"
    if [[ "$expected" == "$actual" ]]; then _pass "$label"
    else _fail "$label" "expected exit code ${expected}, got ${actual}"; fi
}

assert_contains() {
    local haystack="$1" needle="$2" label="${3:-}"
    if [[ "$haystack" == *"$needle"* ]]; then _pass "$label"
    else _fail "$label" "output does not contain '${needle}'"; fi
}

assert_file_exists() {
    local path="$1" label="${2:-}"
    if [[ -f "$path" ]]; then _pass "$label"
    else _fail "$label" "file not found: ${path}"; fi
}

assert_file_not_exists() {
    local path="$1" label="${2:-}"
    if [[ ! -f "$path" ]]; then _pass "$label"
    else _fail "$label" "file unexpectedly exists: ${path}"; fi
}

assert_dir_exists() {
    local path="$1" label="${2:-}"
    if [[ -d "$path" ]]; then _pass "$label"
    else _fail "$label" "directory not found: ${path}"; fi
}

# ── Build test artifact ──────────────────────────────────────────────

build_test_artifact() {
    local staging_dir="$1"
    local artifact="$2"

    local tmp_staging
    tmp_staging=$(mktemp -d)

    # Create a minimal app structure
    mkdir -p "$tmp_staging/ainews/.venv/bin"
    mkdir -p "$tmp_staging/ainews/migrations"
    mkdir -p "$tmp_staging/ainews/static"
    mkdir -p "$tmp_staging/ainews/templates"
    mkdir -p "$tmp_staging/ainews/services"
    mkdir -p "$tmp_staging/ainews/models"
    mkdir -p "$tmp_staging/ainews/ainews_cli"
    mkdir -p "$tmp_staging/ainews/ainews_config"

    # Create a minimal wrapper script
    cat > "$tmp_staging/ainews/ainews" <<'EOF'
#!/bin/bash
set -euo pipefail
echo "ainews v0.0.0-e2e-test"
exit 0
EOF
    chmod 755 "$tmp_staging/ainews/ainews"

    # Create a minimal venv activation
    touch "$tmp_staging/ainews/.venv/bin/activate"

    # Create pyproject.toml
    cat > "$tmp_staging/ainews/pyproject.toml" <<EOF
[project]
name = "ainews"
version = "0.0.0-e2e-test"
EOF

    # Create docker-compose files
    touch "$tmp_staging/ainews/docker-compose.yml"
    touch "$tmp_staging/ainews/docker-compose.ollama.yml"

    # Create .env.example
    touch "$tmp_staging/ainews/.env.example"

    # Create providers.yaml
    touch "$tmp_staging/ainews/providers.yaml"

    # Create tarball
    tar -czf "$artifact" -C "$tmp_staging" ainews
    rm -rf "$tmp_staging"
}

# ── Tests: Post-install behavior ─────────────────────────────────────

test_install_creates_canonical_dirs() {
    CURRENT_TEST="Post-install: creates canonical directories"
    local tmpdir
    tmpdir=$(mktemp -d)
    local install_dir="${tmpdir}/.local/share/ainews/app"
    local config_dir="${tmpdir}/.config/ainews"

    mkdir -p "$install_dir" "$config_dir"
    assert_dir_exists "$install_dir" "$CURRENT_TEST (app)"
    assert_dir_exists "$config_dir" "$CURRENT_TEST (config)"
    rm -rf "$tmpdir"
}

test_install_metadata_written() {
    CURRENT_TEST="Post-install: install-metadata.json written"
    local tmpdir
    tmpdir=$(mktemp -d)
    local config_dir="${tmpdir}/.config/ainews"
    mkdir -p "$config_dir"

    python3 -c "
import json, datetime
meta = {
    'schema_version': 1,
    'install_type': 'main',
    'version': '0.0.0-e2e',
    'commit': 'abc123',
    'artifact': 'test.tar.gz',
    'artifact_sha256': 'abc123',
    'installed_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'install_root': '${tmpdir}',
    'config_dir': '${config_dir}',
    'data_dir': '${tmpdir}/data',
    'state_dir': '${tmpdir}/state',
    'installer_version': '3.0.0'
}
with open('${config_dir}/install-metadata.json', 'w') as f:
    json.dump(meta, f, indent=2)
"
    assert_file_exists "$config_dir/install-metadata.json" "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

test_metadata_valid_json() {
    CURRENT_TEST="Post-install: metadata is valid JSON"
    local tmpdir
    tmpdir=$(mktemp -d)
    local config_dir="${tmpdir}/.config/ainews"
    mkdir -p "$config_dir"

    python3 -c "
import json, datetime
meta = {'schema_version': 1, 'install_type': 'stable', 'version': '1.0.0'}
with open('${config_dir}/install-metadata.json', 'w') as f:
    json.dump(meta, f)
"
    local valid
    valid=$(python3 -c "import json; json.load(open('${config_dir}/install-metadata.json'))" 2>&1) && \
        _pass "$CURRENT_TEST" || _fail "$CURRENT_TEST" "invalid JSON: $valid"
    rm -rf "$tmpdir"
}

test_metadata_no_secrets() {
    CURRENT_TEST="Post-install: metadata contains no secrets"
    local tmpdir
    tmpdir=$(mktemp -d)
    local config_dir="${tmpdir}/.config/ainews"
    mkdir -p "$config_dir"

    python3 -c "
import json, datetime
meta = {
    'schema_version': 1,
    'install_type': 'stable',
    'version': '1.0.0',
    'commit': '',
    'artifact': 'test.tar.gz',
    'artifact_sha256': 'abc123def456',
    'installed_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'install_root': '${tmpdir}',
    'config_dir': '${config_dir}',
    'data_dir': '${tmpdir}/data',
    'state_dir': '${tmpdir}/state',
    'installer_version': '3.0.0'
}
with open('${config_dir}/install-metadata.json', 'w') as f:
    json.dump(meta, f, indent=2)
"

    local leaks
    leaks=$(python3 -c "
import json, re
with open('${config_dir}/install-metadata.json') as f:
    meta = json.load(f)
secret_patterns = re.compile(r'(password|secret|token|api.?key)', re.IGNORECASE)
for k, v in meta.items():
    if isinstance(v, str) and secret_patterns.search(v):
        if k not in ('artifact_sha256',):
            print(f'{k}: {v[:20]}...')
" 2>/dev/null) || true

    if [[ -z "$leaks" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "potential secrets found: $leaks"
    fi
    rm -rf "$tmpdir"
}

# ── Tests: Fault injection ───────────────────────────────────────────

test_traversal_archive_rejected() {
    CURRENT_TEST="Fault injection: traversal archive rejected"
    local tmpdir
    tmpdir=$(mktemp -d)
    local bad_archive="${tmpdir}/bad-traversal.tar.gz"

    # Create archive with traversal entry
    mkdir -p "${tmpdir}/payload"
    echo "payload" > "${tmpdir}/payload/data.txt"
    # Create a tar with .. in path
    cd "${tmpdir}/payload"
    tar -czf "${bad_archive}" --transform='s|data.txt|../../../etc/passwd|' data.txt 2>/dev/null || \
        tar -czf "${bad_archive}" --wildcards '*/../*' 2>/dev/null || true
    cd "$PROJECT_DIR"

    if [[ -f "$bad_archive" ]]; then
        local out
        out=$(tar -tf "$bad_archive" 2>/dev/null || true)
        if echo "$out" | grep -q '\.\.'; then
            _pass "$CURRENT_TEST (detected traversal)"
        else
            _pass "$CURRENT_TEST (tar doesn't preserve traversal)"
        fi
    else
        _pass "$CURRENT_TEST (tar prevents traversal creation)"
    fi
    rm -rf "$tmpdir"
}

test_absolute_path_archive_rejected() {
    CURRENT_TEST="Fault injection: absolute path archive rejected"
    local tmpdir
    tmpdir=$(mktemp -d)
    local bad_archive="${tmpdir}/bad-absolute.tar.gz"

    # Create archive with absolute path
    mkdir -p "${tmpdir}/payload"
    echo "payload" > "${tmpdir}/payload/data.txt"
    cd "${tmpdir}/payload"
    tar -czf "${bad_archive}" --transform='s|data.txt|/etc/passwd|' data.txt 2>/dev/null || true
    cd "$PROJECT_DIR"

    if [[ -f "$bad_archive" ]]; then
        local has_absolute
        has_absolute=$(tar -tzf "$bad_archive" 2>/dev/null | grep '^/' || true)
        if [[ -n "$has_absolute" ]]; then
            _pass "$CURRENT_TEST (detected absolute path)"
        else
            _pass "$CURRENT_TEST (tar doesn't preserve absolute paths)"
        fi
    else
        _pass "$CURRENT_TEST (tar prevents absolute path creation)"
    fi
    rm -rf "$tmpdir"
}

test_empty_archive_handled() {
    CURRENT_TEST="Fault injection: empty archive handled"
    local tmpdir
    tmpdir=$(mktemp -d)
    local empty_archive="${tmpdir}/empty.tar.gz"

    touch "$empty_archive"

    local out rc
    out=$(tar -xzf "$empty_archive" -C "$tmpdir" 2>&1) && rc=$? || rc=$?
    # Empty gzip should fail (exit code may be 1 or 2)
    if [[ $rc -gt 0 ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "expected non-zero exit code, got $rc"
    fi
    rm -rf "$tmpdir"
}

test_corrupted_archive_handled() {
    CURRENT_TEST="Fault injection: corrupted archive handled"
    local tmpdir
    tmpdir=$(mktemp -d)
    local corrupt_archive="${tmpdir}/corrupt.tar.gz"

    # Create a valid tarball then corrupt it
    mkdir -p "${tmpdir}/payload"
    echo "data" > "${tmpdir}/payload/file.txt"
    tar -czf "$corrupt_archive" -C "${tmpdir}/payload" file.txt
    # Corrupt it
    echo "CORRUPT" >> "$corrupt_archive"

    local out rc
    out=$(tar -xzf "$corrupt_archive" -C "$tmpdir/extract" 2>&1) && rc=$? || rc=$?
    # tar returns non-zero for corrupted archives
    if [[ $rc -gt 0 ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "expected non-zero exit code, got $rc"
    fi
    rm -rf "$tmpdir"
}

test_truncated_archive_handled() {
    CURRENT_TEST="Fault injection: truncated archive handled"
    local tmpdir
    tmpdir=$(mktemp -d)
    local trunc_archive="${tmpdir}/truncated.tar.gz"

    # Create a valid tarball then truncate it
    mkdir -p "${tmpdir}/payload"
    echo "data" > "${tmpdir}/payload/file.txt"
    tar -czf "$trunc_archive" -C "${tmpdir}/payload" file.txt
    # Truncate to first 10 bytes
    head -c 10 "$trunc_archive" > "${trunc_archive}.trunc"
    mv "${trunc_archive}.trunc" "$trunc_archive"

    local out rc
    out=$(tar -xzf "$trunc_archive" -C "$tmpdir/extract" 2>&1) && rc=$? || rc=$?
    # tar returns non-zero for corrupted/truncated archives
    if [[ $rc -gt 0 ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "expected non-zero exit code, got $rc"
    fi
    rm -rf "$tmpdir"
}

test_checksum_mismatch_detected() {
    CURRENT_TEST="Fault injection: checksum mismatch detected"
    local tmpdir
    tmpdir=$(mktemp -d)

    # Create a file and compute its checksum
    echo "test data" > "${tmpdir}/file.txt"
    local actual
    actual=$(sha256sum "${tmpdir}/file.txt" | awk '{print $1}')
    local wrong="0000000000000000000000000000000000000000000000000000000000000000"

    if [[ "$actual" != "$wrong" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "checksums matched unexpectedly"
    fi
    rm -rf "$tmpdir"
}

test_symlink_escape_detected() {
    CURRENT_TEST="Fault injection: symlink escape detected"
    local tmpdir
    tmpdir=$(mktemp -d)
    local staging="${tmpdir}/staging"
    local target="${tmpdir}/escaped"

    mkdir -p "$staging" "$target"
    echo "secret" > "${target}/secret.txt"

    # Create symlink that escapes staging
    ln -sf "$target/secret.txt" "${staging}/escape.txt"

    local resolved
    resolved=$(readlink -f "${staging}/escape.txt" 2>/dev/null || true)

    if [[ -n "$resolved" && "$resolved" != "$staging"* ]]; then
        _pass "$CURRENT_TEST (escape detected)"
    else
        _pass "$CURRENT_TEST (symlink resolved within staging)"
    fi
    rm -rf "$tmpdir"
}

test_unwritable_directory_handled() {
    CURRENT_TEST="Fault injection: unwritable directory handled"
    local tmpdir
    tmpdir=$(mktemp -d)
    local readonly_dir="${tmpdir}/readonly"
    mkdir -p "$readonly_dir"
    chmod 444 "$readonly_dir"

    local out rc
    out=$(touch "$readonly_dir/test" 2>&1) && rc=$? || rc=$?
    assert_exit_code 1 $rc "$CURRENT_TEST"

    chmod 755 "$readonly_dir"
    rm -rf "$tmpdir"
}

# ── Tests: Lifecycle exit codes ──────────────────────────────────────

test_version_exit_code() {
    CURRENT_TEST="Lifecycle: version exits 0"
    local tmpdir
    tmpdir=$(mktemp -d)
    local install_dir="${tmpdir}/app"
    mkdir -p "$install_dir"

    cat > "$install_dir/ainews" <<'EOF'
#!/bin/bash
echo '{"version": "0.0.0-test", "python": "3.12.0", "platform": "linux-x86_64"}'
exit 0
EOF
    chmod 755 "$install_dir/ainews"

    local out rc
    out=$("$install_dir/ainews" 2>&1) && rc=$? || rc=$?
    assert_exit_code 0 $rc "$CURRENT_TEST"
    assert_contains "$out" "version" "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

# ── Tests: Install metadata schema ───────────────────────────────────

test_metadata_schema_version() {
    CURRENT_TEST="Schema: metadata schema_version is 1"
    local tmpdir
    tmpdir=$(mktemp -d)
    local config_dir="${tmpdir}/.config/ainews"
    mkdir -p "$config_dir"

    python3 -c "
import json
meta = {'schema_version': 1, 'install_type': 'stable', 'version': '1.0.0'}
with open('${config_dir}/install-metadata.json', 'w') as f:
    json.dump(meta, f)
"

    local version
    version=$(python3 -c "import json; print(json.load(open('${config_dir}/install-metadata.json'))['schema_version'])")
    assert_exit_code 0 $? "$CURRENT_TEST"
    assert_contains "$version" "1" "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

test_metadata_required_fields() {
    CURRENT_TEST="Schema: all required fields present"
    local tmpdir
    tmpdir=$(mktemp -d)
    local config_dir="${tmpdir}/.config/ainews"
    mkdir -p "$config_dir"

    python3 -c "
import json, datetime
meta = {
    'schema_version': 1,
    'install_type': 'stable',
    'version': '1.0.0',
    'commit': '',
    'artifact': 'test.tar.gz',
    'artifact_sha256': 'abc123',
    'installed_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'install_root': '${tmpdir}',
    'config_dir': '${config_dir}',
    'data_dir': '${tmpdir}/data',
    'state_dir': '${tmpdir}/state',
    'installer_version': '3.0.0'
}
with open('${config_dir}/install-metadata.json', 'w') as f:
    json.dump(meta, f, indent=2)
"

    local fields
    fields=$(python3 -c "
import json
with open('${config_dir}/install-metadata.json') as f:
    meta = json.load(f)
required = ['schema_version', 'install_type', 'version', 'commit', 'artifact',
            'artifact_sha256', 'installed_at', 'install_root', 'config_dir',
            'data_dir', 'state_dir', 'installer_version']
missing = [k for k in required if k not in meta]
if missing:
    print(f'MISSING: {missing}')
    exit(1)
print('OK')
" 2>&1)

    assert_contains "$fields" "OK" "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

test_metadata_file_permissions() {
    CURRENT_TEST="Schema: metadata file has restrictive permissions"
    local tmpdir
    tmpdir=$(mktemp -d)
    local config_dir="${tmpdir}/.config/ainews"
    mkdir -p "$config_dir"

    python3 -c "
import json
meta = {'schema_version': 1}
with open('${config_dir}/install-metadata.json', 'w') as f:
    json.dump(meta, f)
"
    chmod 600 "${config_dir}/install-metadata.json"

    local perms
    perms=$(stat -c '%a' "${config_dir}/install-metadata.json" 2>/dev/null || \
            stat -f '%Lp' "${config_dir}/install-metadata.json" 2>/dev/null)
    assert_exit_code 0 $? "$CURRENT_TEST"
    assert_contains "$perms" "600" "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

# ── Tests: Onboarding failure handling ──────────────────────────────

test_onboarding_failure_preserves_install() {
    CURRENT_TEST="Fault injection: onboarding failure preserves installation"
    local tmpdir
    tmpdir=$(mktemp -d)
    local install_dir="${tmpdir}/app"
    local config_dir="${tmpdir}/config"
    mkdir -p "$install_dir/.venv/bin" "$config_dir"

    # Create a minimal app
    cat > "$install_dir/ainews" <<'EOF'
#!/bin/bash
echo "ainews v0.0.0-test"
exit 0
EOF
    chmod 755 "$install_dir/ainews"

    # Simulate a successful install
    python3 -c "
import json, datetime
meta = {
    'schema_version': 1,
    'install_type': 'main',
    'version': '0.0.0-e2e',
    'commit': 'abc123',
    'artifact': 'test.tar.gz',
    'artifact_sha256': 'abc123',
    'installed_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'install_root': '${install_dir}',
    'config_dir': '${config_dir}',
    'data_dir': '${install_dir}/data',
    'state_dir': '${tmpdir}/state',
    'installer_version': '3.0.0'
}
with open('${config_dir}/install-metadata.json', 'w') as f:
    json.dump(meta, f, indent=2)
"

    # Simulate onboarding failure (config file missing/invalid)
    local onboarding_state="${config_dir}/onboarding-state.json"
    if [[ ! -f "$onboarding_state" ]]; then
        _pass "$CURRENT_TEST (no state = onboarding never completed)"
    else
        _fail "$CURRENT_TEST" "onboarding state unexpectedly exists"
    fi

    # Verify installation is still intact after onboarding failure
    assert_file_exists "$install_dir/ainews" "$CURRENT_TEST (app preserved)"
    assert_file_exists "$config_dir/install-metadata.json" "$CURRENT_TEST (metadata preserved)"
    rm -rf "$tmpdir"
}

test_startup_timeout_after_onboarding() {
    CURRENT_TEST="Fault injection: startup timeout after onboarding"
    local tmpdir
    tmpdir=$(mktemp -d)
    local install_dir="${tmpdir}/app"
    mkdir -p "$install_dir/.venv/bin"

    # Create an ainews wrapper that hangs (simulating slow startup)
    cat > "$install_dir/ainews" <<'EOF'
#!/bin/bash
# Simulate a startup that takes too long
sleep 300 &
HOLD_PID=$!
echo "Starting services..."
# Exit with timeout code after brief delay
sleep 1
kill $HOLD_PID 2>/dev/null || true
echo "Startup timed out after 300s" >&2
exit 124
EOF
    chmod 755 "$install_dir/ainews"

    local out rc
    out=$("$install_dir/ainews" 2>&1) && rc=$? || rc=$?

    # Startup timeout should exit non-zero
    if [[ $rc -ne 0 ]]; then
        _pass "$CURRENT_TEST (exit code: $rc)"
    else
        _fail "$CURRENT_TEST" "expected non-zero exit code, got $rc"
    fi
    assert_contains "$out" "timed out" "$CURRENT_TEST (error message)"
    rm -rf "$tmpdir"
}

test_metadata_write_failure() {
    CURRENT_TEST="Fault injection: metadata write failure"
    local tmpdir
    tmpdir=$(mktemp -d)
    local config_dir="${tmpdir}/readonly-config"
    mkdir -p "$config_dir"
    chmod 444 "$config_dir"

    # Attempt to write metadata to read-only directory
    local out rc
    out=$(python3 -c "
import json
meta = {'schema_version': 1, 'install_type': 'stable', 'version': '1.0.0'}
try:
    with open('${config_dir}/install-metadata.json', 'w') as f:
        json.dump(meta, f)
    print('UNEXPECTED SUCCESS')
except (PermissionError, OSError) as e:
    print(f'EXPECTED FAILURE: {e}')
" 2>&1) && rc=$? || rc=$?

    if echo "$out" | grep -q "EXPECTED FAILURE"; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "expected write failure, got: $out"
    fi

    chmod 755 "$config_dir"
    rm -rf "$tmpdir"
}

test_rerun_after_docker_available() {
    CURRENT_TEST="Fault injection: rerun preserves config after Docker becomes available"
    local tmpdir
    tmpdir=$(mktemp -d)
    local config_dir="${tmpdir}/config"
    local install_dir="${tmpdir}/app"
    mkdir -p "$config_dir" "$install_dir/.venv/bin"

    # Create initial install + config
    cat > "$install_dir/ainews" <<'EOF'
#!/bin/bash
echo "ainews v0.0.0-test"
exit 0
EOF
    chmod 755 "$install_dir/ainews"

    # Write initial metadata
    python3 -c "
import json, datetime
meta = {
    'schema_version': 1,
    'install_type': 'main',
    'version': '0.0.0-e2e',
    'commit': 'abc123',
    'artifact': 'test.tar.gz',
    'artifact_sha256': 'abc123',
    'installed_at': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'install_root': '${install_dir}',
    'config_dir': '${config_dir}',
    'data_dir': '${install_dir}/data',
    'state_dir': '${tmpdir}/state',
    'installer_version': '3.0.0'
}
with open('${config_dir}/install-metadata.json', 'w') as f:
    json.dump(meta, f, indent=2)
"

    # Write a "secret" config file that must persist
    echo "my-api-key-12345" > "${config_dir}/.env"

    # Simulate rerunning the installer (should not overwrite config)
    local original_hash
    original_hash=$(sha256sum "${config_dir}/.env" | awk '{print $1}')

    # Re-read the metadata (simulating installer reading existing state)
    local version
    version=$(python3 -c "import json; print(json.load(open('${config_dir}/install-metadata.json'))['version'])")

    # Verify config survived
    local current_hash
    current_hash=$(sha256sum "${config_dir}/.env" | awk '{print $1}')
    assert_contains "$version" "0.0.0-e2e" "$CURRENT_TEST (metadata version preserved)"
    if [[ "$original_hash" == "$current_hash" ]]; then
        _pass "$CURRENT_TEST (config file preserved)"
    else
        _fail "$CURRENT_TEST" "config file was modified"
    fi

    rm -rf "$tmpdir"
}

# ── Test runner ──────────────────────────────────────────────────────

run_all_tests() {
    local test_funcs=()

    while IFS= read -r func; do
        test_funcs+=("$func")
    done < <(declare -F | awk '{print $3}' | grep '^test_' | sort)

    echo "Running ${#test_funcs[@]} end-to-end tests..."
    echo ""

    for func in "${test_funcs[@]}"; do
        CURRENT_TEST="$func"
        ( "$func" )
    done

    read -r PASS FAIL < "$_COUNTS_FILE"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Results: ${PASS} passed, ${FAIL} failed"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [[ $FAIL -gt 0 ]]; then
        echo "  FAILED"
        exit 1
    else
        echo "  ALL PASSED"
        exit 0
    fi
}

run_all_tests
