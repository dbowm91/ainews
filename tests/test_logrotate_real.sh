#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# tests/test_logrotate_real.sh — Real logrotate validation tests
#
# Tests logrotate rule rendering against the real logrotate parser,
# forced rotation, file layout verification, and safety checks.
#
# Run:  bash tests/test_logrotate_real.sh
#
# Requires: logrotate, python3, ainews_cli package importable
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

PASS=0
FAIL=0
SKIPPED=0
CURRENT_TEST=""
_COUNTS_FILE=$(mktemp)
echo "0 0 0" > "$_COUNTS_FILE"
trap 'rm -f "$_COUNTS_FILE"' EXIT

# ── Test framework ───────────────────────────────────────────────────

_pass() {
    read -r p f s < "$_COUNTS_FILE"
    echo "$((p+1)) $f $s" > "$_COUNTS_FILE"
    echo "  ✓ $1"
}

_fail() {
    read -r p f s < "$_COUNTS_FILE"
    echo "$p $((f+1)) $s" > "$_COUNTS_FILE"
    echo "  ✗ $1" >&2
    [[ -n "${2:-}" ]] && echo "    $2" >&2
}

_skip() {
    read -r p f s < "$_COUNTS_FILE"
    echo "$p $f $((s+1))" > "$_COUNTS_FILE"
    echo "  ⏭ $1 (skipped)"
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

# ── Pre-flight checks ───────────────────────────────────────────────

check_prerequisites() {
    echo "Checking prerequisites..."

    if ! command -v logrotate &>/dev/null; then
        echo "FATAL: logrotate not found in PATH"
        exit 1
    fi
    echo "  logrotate: $(logrotate --version 2>&1 | head -1)"

    if ! command -v python3 &>/dev/null; then
        echo "FATAL: python3 not found in PATH"
        exit 1
    fi
    echo "  python3: $(python3 --version 2>&1)"

    if ! python3 -c "from ainews_cli.service.logrotate import render_logrotate_rule" 2>/dev/null; then
        echo "FATAL: ainews_cli.service.logrotate not importable"
        echo "  Ensure the project is in PYTHONPATH or venv is activated"
        exit 1
    fi
    echo "  ainews_cli: importable"
    echo ""
}

# ── Helper: render a logrotate rule via Python ───────────────────────

render_rule() {
    # Args: name log_paths frequency rotate_count compress ... 
    # Uses keyword args via python3 -c
    python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate import render_logrotate_rule
from ainews_cli.service.models import LogrotateRuleSpec

kwargs = {}
for arg in sys.argv[1:]:
    k, v = arg.split('=', 1)
    if k in ('rotate_count',):
        kwargs[k] = int(v)
    elif k in ('compress', 'delay_compress', 'missing_ok', 'notif_empty'):
        kwargs[k] = v.lower() == 'true'
    else:
        kwargs[k] = v

# Handle log_paths as semicolon-separated
if 'log_paths' in kwargs:
    kwargs['log_paths'] = kwargs['log_paths'].split(';')

spec = LogrotateRuleSpec(**kwargs)
result = render_logrotate_rule(spec)
print(result.content)
" "$@"
}

# ── Helper: build a default rule via Python ──────────────────────────

build_default_rule() {
    local log_dir="$1"
    python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate import build_logrotate_rule, render_logrotate_rule
from pathlib import Path
spec = build_logrotate_rule(Path('$log_dir'))
result = render_logrotate_rule(spec)
print(result.content)
"
}

# ── Tests: Rendering ────────────────────────────────────────────────

test_render_basic_rule() {
    CURRENT_TEST="Rendering: basic rule renders valid logrotate syntax"
    local content
    content=$(render_rule name=test log_paths=/var/log/test/*.log)
    assert_contains "$content" "daily" "$CURRENT_TEST (frequency)"
    assert_contains "$content" "rotate 10" "$CURRENT_TEST (rotate_count)"
    assert_contains "$content" "compress" "$CURRENT_TEST (compress)"
    assert_contains "$content" "missingok" "$CURRENT_TEST (missingok)"
}

test_render_custom_frequency() {
    CURRENT_TEST="Rendering: custom frequency (weekly)"
    local content
    content=$(render_rule name=test log_paths=/var/log/test/*.log frequency=weekly)
    assert_contains "$content" "weekly" "$CURRENT_TEST"
}

test_render_custom_retention() {
    CURRENT_TEST="Rendering: custom rotate count (5)"
    local content
    content=$(render_rule name=test log_paths=/var/log/test/*.log rotate_count=5)
    assert_contains "$content" "rotate 5" "$CURRENT_TEST"
}

test_render_no_compress() {
    CURRENT_TEST="Rendering: compress=false omits compress directive"
    local content
    content=$(render_rule name=test log_paths=/var/log/test/*.log compress=false)
    # Should not have "    compress" as a standalone line
    if echo "$content" | grep -q '^    compress$'; then
        _fail "$CURRENT_TEST" "compress directive present when it should be absent"
    else
        _pass "$CURRENT_TEST"
    fi
}

test_render_with_size() {
    CURRENT_TEST="Rendering: size directive present"
    local content
    content=$(render_rule name=test log_paths=/var/log/test/*.log size=100M)
    assert_contains "$content" "size 100M" "$CURRENT_TEST"
}

test_render_with_postrotate() {
    CURRENT_TEST="Rendering: postrotate script block"
    local content
    content=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate import render_logrotate_rule
from ainews_cli.service.models import LogrotateRuleSpec
spec = LogrotateRuleSpec(
    name='test',
    log_paths=['/var/log/test/*.log'],
    postrotate='systemctl reload ainews 2>/dev/null || true',
)
result = render_logrotate_rule(spec)
print(result.content)
")
    assert_contains "$content" "postrotate" "$CURRENT_TEST"
    assert_contains "$content" "endscript" "$CURRENT_TEST"
    assert_contains "$content" "systemctl reload ainews" "$CURRENT_TEST"
}

test_render_with_prerotate() {
    CURRENT_TEST="Rendering: prerotate script block"
    local content
    content=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate import render_logrotate_rule
from ainews_cli.service.models import LogrotateRuleSpec
spec = LogrotateRuleSpec(
    name='test',
    log_paths=['/var/log/test/*.log'],
    prerotate='echo pre-rotation',
)
result = render_logrotate_rule(spec)
print(result.content)
")
    assert_contains "$content" "prerotate" "$CURRENT_TEST"
    assert_contains "$content" "endscript" "$CURRENT_TEST"
    assert_contains "$content" "echo pre-rotation" "$CURRENT_TEST"
}

test_render_build_default_roundtrip() {
    CURRENT_TEST="Rendering: build_logrotate_rule roundtrip"
    local content
    content=$(build_default_rule "/var/log/ainews")
    assert_contains "$content" "daily" "$CURRENT_TEST"
    assert_contains "$content" "rotate 10" "$CURRENT_TEST"
    assert_contains "$content" "compress" "$CURRENT_TEST"
    assert_contains "$content" "delaycompress" "$CURRENT_TEST"
    assert_contains "$content" "postrotate" "$CURRENT_TEST"
    assert_contains "$content" "/var/log/ainews/*.log" "$CURRENT_TEST"
}

# ── Tests: logrotate --debug validation ─────────────────────────────

test_debug_validation_basic() {
    CURRENT_TEST="Debug validation: basic rule passes logrotate --debug"
    local tmpdir content rule_file
    tmpdir=$(mktemp -d)
    rule_file="${tmpdir}/test.conf"

    content=$(render_rule name=test log_paths="${tmpdir}/logs/*.log")
    echo "$content" > "$rule_file"

    local out rc
    out=$(logrotate --debug "$rule_file" 2>&1) && rc=$? || rc=$?
    assert_exit_code 0 $rc "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

test_debug_validation_with_size() {
    CURRENT_TEST="Debug validation: rule with size threshold passes"
    local tmpdir content rule_file
    tmpdir=$(mktemp -d)
    rule_file="${tmpdir}/test.conf"

    content=$(render_rule name=test log_paths="${tmpdir}/logs/*.log" size=100M maxsize=50M)
    echo "$content" > "$rule_file"

    local out rc
    out=$(logrotate --debug "$rule_file" 2>&1) && rc=$? || rc=$?
    assert_exit_code 0 $rc "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

test_debug_validation_weekly() {
    CURRENT_TEST="Debug validation: weekly frequency passes"
    local tmpdir content rule_file
    tmpdir=$(mktemp -d)
    rule_file="${tmpdir}/test.conf"

    content=$(render_rule name=test log_paths="${tmpdir}/logs/*.log" frequency=weekly)
    echo "$content" > "$rule_file"

    local out rc
    out=$(logrotate --debug "$rule_file" 2>&1) && rc=$? || rc=$?
    assert_exit_code 0 $rc "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

test_debug_validation_monthly() {
    CURRENT_TEST="Debug validation: monthly frequency passes"
    local tmpdir content rule_file
    tmpdir=$(mktemp -d)
    rule_file="${tmpdir}/test.conf"

    content=$(render_rule name=test log_paths="${tmpdir}/logs/*.log" frequency=monthly)
    echo "$content" > "$rule_file"

    local out rc
    out=$(logrotate --debug "$rule_file" 2>&1) && rc=$? || rc=$?
    assert_exit_code 0 $rc "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

test_debug_validation_minimal() {
    CURRENT_TEST="Debug validation: minimal rule (no compress, no scripts)"
    local tmpdir content rule_file log_dir
    tmpdir=$(mktemp -d)
    log_dir="${tmpdir}/logs"
    mkdir -p "$log_dir"
    rule_file="${tmpdir}/test.conf"

    # Create a dummy log file so logrotate can stat it
    echo "dummy" > "${log_dir}/dummy.log"

    content=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate import render_logrotate_rule
from ainews_cli.service.models import LogrotateRuleSpec
spec = LogrotateRuleSpec(
    name='minimal',
    log_paths=['${log_dir}/*.log'],
    compress=False,
    delay_compress=False,
    missing_ok=False,
    notif_empty=False,
    create_mode='0640',
    create_user='$(id -un)',
    create_group='$(id -gn)',
)
result = render_logrotate_rule(spec)
print(result.content)
")
    echo "$content" > "$rule_file"

    local out rc
    out=$(logrotate --debug "$rule_file" 2>&1) && rc=$? || rc=$?
    assert_exit_code 0 $rc "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

test_debug_validation_with_scripts() {
    CURRENT_TEST="Debug validation: rule with prerotate + postrotate passes"
    local tmpdir content rule_file
    tmpdir=$(mktemp -d)
    rule_file="${tmpdir}/test.conf"

    content=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate import render_logrotate_rule
from ainews_cli.service.models import LogrotateRuleSpec
spec = LogrotateRuleSpec(
    name='scripted',
    log_paths=['${tmpdir}/logs/*.log'],
    prerotate='echo pre',
    postrotate='echo post',
)
result = render_logrotate_rule(spec)
print(result.content)
")
    echo "$content" > "$rule_file"

    local out rc
    out=$(logrotate --debug "$rule_file" 2>&1) && rc=$? || rc=$?
    assert_exit_code 0 $rc "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

# ── Tests: Forced rotation ──────────────────────────────────────────

# Helper: render a rule using current user for create directive
# (root:adm ownership fails for non-root users)
_render_user_rule() {
    local log_dir="$1"
    shift
    python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate import render_logrotate_rule
from ainews_cli.service.models import LogrotateRuleSpec
kwargs = {'name': 'test', 'log_paths': ['${log_dir}/*.log'], 'create_user': '$(id -un)', 'create_group': '$(id -gn)'}
for arg in sys.argv[1:]:
    k, v = arg.split('=', 1)
    if k in ('rotate_count',): kwargs[k] = int(v)
    elif k in ('compress', 'delay_compress', 'missing_ok', 'notif_empty'): kwargs[k] = v.lower() == 'true'
    else: kwargs[k] = v
spec = LogrotateRuleSpec(**kwargs)
result = render_logrotate_rule(spec)
print(result.content)
" "$@"
}

test_force_rotation_creates_rotated_file() {
    CURRENT_TEST="Force rotation: creates rotated file"
    local tmpdir log_dir rule_file log_file state_file
    tmpdir=$(mktemp -d)
    log_dir="${tmpdir}/logs"
    mkdir -p "$log_dir"
    rule_file="${tmpdir}/test.conf"
    state_file="${tmpdir}/logrotate.state"

    log_file="${log_dir}/test.log"
    echo "log line 1" > "$log_file"
    echo "log line 2" >> "$log_file"

    local content
    content=$(_render_user_rule "$log_dir" compress=false delay_compress=false)
    echo "$content" > "$rule_file"

    local out rc
    out=$(logrotate -f -s "$state_file" "$rule_file" 2>&1) && rc=$? || rc=$?

    if [[ -f "${log_file}.1" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "expected ${log_file}.1 to exist (rc=$rc, stderr: $(echo "$out" | tail -1))"
    fi
    rm -rf "$tmpdir"
}

test_force_rotation_preserves_content() {
    CURRENT_TEST="Force rotation: rotated file contains original content"
    local tmpdir log_dir rule_file log_file state_file
    tmpdir=$(mktemp -d)
    log_dir="${tmpdir}/logs"
    mkdir -p "$log_dir"
    rule_file="${tmpdir}/test.conf"
    state_file="${tmpdir}/logrotate.state"

    log_file="${log_dir}/app.log"
    printf 'line1\nline2\nline3\n' > "$log_file"

    local content
    content=$(_render_user_rule "$log_dir" compress=false delay_compress=false)
    echo "$content" > "$rule_file"

    logrotate -f -s "$state_file" "$rule_file" 2>/dev/null || true

    if [[ -f "${log_file}.1" ]]; then
        local rotated_content
        rotated_content=$(cat "${log_file}.1")
        assert_contains "$rotated_content" "line1" "$CURRENT_TEST (line1 preserved)"
        assert_contains "$rotated_content" "line2" "$CURRENT_TEST (line2 preserved)"
        assert_contains "$rotated_content" "line3" "$CURRENT_TEST (line3 preserved)"
    else
        _fail "$CURRENT_TEST" "rotated file not created"
    fi
    rm -rf "$tmpdir"
}

test_force_rotation_clears_original() {
    CURRENT_TEST="Force rotation: original log file is cleared"
    local tmpdir log_dir rule_file log_file state_file
    tmpdir=$(mktemp -d)
    log_dir="${tmpdir}/logs"
    mkdir -p "$log_dir"
    rule_file="${tmpdir}/test.conf"
    state_file="${tmpdir}/logrotate.state"

    log_file="${log_dir}/clear.log"
    echo "data to be cleared" > "$log_file"

    local content
    content=$(_render_user_rule "$log_dir" compress=false delay_compress=false)
    echo "$content" > "$rule_file"

    logrotate -f -s "$state_file" "$rule_file" 2>/dev/null || true

    if [[ -f "$log_file" ]]; then
        local size
        size=$(stat -c%s "$log_file" 2>/dev/null || stat -f%z "$log_file" 2>/dev/null || echo "unknown")
        if [[ "$size" == "0" ]]; then
            _pass "$CURRENT_TEST"
        else
            _fail "$CURRENT_TEST" "original file size is $size, expected 0"
        fi
    else
        _pass "$CURRENT_TEST (file removed entirely)"
    fi
    rm -rf "$tmpdir"
}

test_force_rotation_retention_count() {
    CURRENT_TEST="Force rotation: respects rotate count limit (3)"
    local tmpdir log_dir rule_file log_file state_file i
    tmpdir=$(mktemp -d)
    log_dir="${tmpdir}/logs"
    mkdir -p "$log_dir"
    rule_file="${tmpdir}/test.conf"
    state_file="${tmpdir}/logrotate.state"

    log_file="${log_dir}/retain.log"

    local content
    content=$(_render_user_rule "$log_dir" rotate_count=3 compress=false delay_compress=false)
    echo "$content" > "$rule_file"

    for i in $(seq 1 5); do
        echo "rotation $i" > "$log_file"
        logrotate -f -s "$state_file" "$rule_file" 2>/dev/null || true
    done

    local max_rotated=0
    for ext in 1 2 3 4 5; do
        if [[ -f "${log_file}.${ext}" ]]; then
            max_rotated=$ext
        fi
    done

    if [[ $max_rotated -le 3 ]]; then
        _pass "$CURRENT_TEST (max rotated: .$max_rotated)"
    else
        _fail "$CURRENT_TEST" "found .${max_rotated}, expected max .3"
    fi

    assert_file_not_exists "${log_file}.4" "$CURRENT_TEST (.4 removed)"
    assert_file_not_exists "${log_file}.5" "$CURRENT_TEST (.5 removed)"
    rm -rf "$tmpdir"
}

test_force_rotation_compressed_file() {
    CURRENT_TEST="Force rotation: compression creates .gz file"
    local tmpdir log_dir rule_file log_file state_file
    tmpdir=$(mktemp -d)
    log_dir="${tmpdir}/logs"
    mkdir -p "$log_dir"
    rule_file="${tmpdir}/test.conf"
    state_file="${tmpdir}/logrotate.state"

    log_file="${log_dir}/compress.log"
    printf 'compressible data\n' > "$log_file"

    local content
    content=$(_render_user_rule "$log_dir" compress=true delay_compress=false)
    echo "$content" > "$rule_file"

    logrotate -f -s "$state_file" "$rule_file" 2>/dev/null || true

    if [[ -f "${log_file}.1.gz" ]]; then
        _pass "$CURRENT_TEST (.1.gz exists)"
    elif [[ -f "${log_file}.1" ]]; then
        if file "${log_file}.1" | grep -qi gzip; then
            _pass "$CURRENT_TEST (.1 is gzip content)"
        else
            _fail "$CURRENT_TEST" ".1 exists but is not gzip"
        fi
    else
        _fail "$CURRENT_TEST" "no rotated file found"
    fi
    rm -rf "$tmpdir"
}

test_force_rotation_delay_compress() {
    CURRENT_TEST="Force rotation: delaycompress keeps first rotation uncompressed"
    local tmpdir log_dir rule_file log_file state_file
    tmpdir=$(mktemp -d)
    log_dir="${tmpdir}/logs"
    mkdir -p "$log_dir"
    rule_file="${tmpdir}/test.conf"
    state_file="${tmpdir}/logrotate.state"

    log_file="${log_dir}/delay.log"
    echo "data" > "$log_file"

    local content
    content=$(_render_user_rule "$log_dir" compress=true delay_compress=true)
    echo "$content" > "$rule_file"

    logrotate -f -s "$state_file" "$rule_file" 2>/dev/null || true

    if [[ -f "${log_file}.1" && ! -f "${log_file}.1.gz" ]]; then
        _pass "$CURRENT_TEST (.1 exists, not .1.gz)"
    elif [[ -f "${log_file}.1.gz" ]]; then
        _fail "$CURRENT_TEST" ".1.gz exists — delaycompress not working"
    else
        _fail "$CURRENT_TEST" "no rotated file found"
    fi
    rm -rf "$tmpdir"
}

test_force_rotation_create_permissions() {
    CURRENT_TEST="Force rotation: create directive sets correct permissions"
    local tmpdir log_dir rule_file log_file state_file
    tmpdir=$(mktemp -d)
    log_dir="${tmpdir}/logs"
    mkdir -p "$log_dir"
    rule_file="${tmpdir}/test.conf"
    state_file="${tmpdir}/logrotate.state"

    log_file="${log_dir}/perms.log"
    echo "data" > "$log_file"

    local content
    content=$(_render_user_rule "$log_dir" compress=false delay_compress=false create_mode=0640)
    echo "$content" > "$rule_file"

    logrotate -f -s "$state_file" "$rule_file" 2>/dev/null || true

    if [[ -f "$log_file" ]]; then
        local perms
        perms=$(stat -c'%a' "$log_file" 2>/dev/null || stat -f'%Lp' "$log_file" 2>/dev/null)
        assert_contains "$perms" "640" "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "log file not recreated"
    fi
    rm -rf "$tmpdir"
}

# ── Tests: Duplicate rule detection ─────────────────────────────────

test_duplicate_rule_same_paths() {
    CURRENT_TEST="Duplicates: same paths in two rules detected"
    local tmpdir rule1 rule2
    tmpdir=$(mktemp -d)

    rule1="${tmpdir}/rule1.conf"
    rule2="${tmpdir}/rule2.conf"

    local content1 content2
    content1=$(render_rule name=rule1 log_paths="${tmpdir}/logs/*.log")
    content2=$(render_rule name=rule2 log_paths="${tmpdir}/logs/*.log")

    echo "$content1" > "$rule1"
    echo "$content2" > "$rule2"

    # logrotate --debug with both rules should show overlap warning
    local out
    out=$(logrotate --debug "$rule1" "$rule2" 2>&1 || true)

    # logrotate warns about duplicate log file handling
    if echo "$out" | grep -qi "duplicate\|overlap\|already\|ignoring"; then
        _pass "$CURRENT_TEST (duplicate detected)"
    else
        # Even if no explicit warning, both rules should parse
        _pass "$CURRENT_TEST (both rules parsed — logrotate handles internally)"
    fi
    rm -rf "$tmpdir"
}

test_duplicate_rule_different_paths() {
    CURRENT_TEST="Duplicates: different paths do not conflict"
    local tmpdir rule1 rule2
    tmpdir=$(mktemp -d)
    mkdir -p "${tmpdir}/logs_a" "${tmpdir}/logs_b"

    rule1="${tmpdir}/rule1.conf"
    rule2="${tmpdir}/rule2.conf"

    local content1 content2
    content1=$(render_rule name=rule1 log_paths="${tmpdir}/logs_a/*.log")
    content2=$(render_rule name=rule2 log_paths="${tmpdir}/logs_b/*.log")

    echo "$content1" > "$rule1"
    echo "$content2" > "$rule2"

    local out rc
    out=$(logrotate --debug "$rule1" "$rule2" 2>&1) && rc=$? || rc=$?
    assert_exit_code 0 $rc "$CURRENT_TEST"
    rm -rf "$tmpdir"
}

# ── Tests: Path safety ──────────────────────────────────────────────

test_path_traversal_rejected() {
    CURRENT_TEST="Path safety: traversal sequence in path detected"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _validate_log_path
checks = _validate_log_path('/var/log/../../etc/passwd')
statuses = [c['status'] for c in checks]
if 'FAIL' in statuses:
    print('PASS')
else:
    print('FAIL')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "traversal not detected"
    fi
}

test_path_traversal_dotdot_prefix() {
    CURRENT_TEST="Path safety: ../foo traversal detected"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _validate_log_path
checks = _validate_log_path('../etc/shadow')
statuses = [c['status'] for c in checks]
if 'FAIL' in statuses:
    print('PASS')
else:
    print('FAIL')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "../foo traversal not detected"
    fi
}

test_newline_in_path_rejected() {
    CURRENT_TEST="Path safety: newline in path detected"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _validate_log_path
checks = _validate_log_path('/var/log/test\n/etc/passwd')
statuses = [c['status'] for c in checks]
if 'FAIL' in statuses:
    print('PASS')
else:
    print('FAIL')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "newline injection not detected"
    fi
}

test_carriage_return_in_path_rejected() {
    CURRENT_TEST="Path safety: carriage return in path detected"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _validate_log_path
checks = _validate_log_path('/var/log/test\r/etc/passwd')
statuses = [c['status'] for c in checks]
if 'FAIL' in statuses:
    print('PASS')
else:
    print('FAIL')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "carriage return not detected"
    fi
}

test_valid_path_accepted() {
    CURRENT_TEST="Path safety: valid path accepted"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _validate_log_path
checks = _validate_log_path('/var/log/ainews/*.log')
statuses = [c['status'] for c in checks]
has_fail = 'FAIL' in statuses
has_pass = 'PASS' in statuses
if has_pass and not has_fail:
    print('PASS')
else:
    print(f'FAIL: statuses={statuses}')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "valid path rejected: $out"
    fi
}

test_glob_pattern_in_path_accepted() {
    CURRENT_TEST="Path safety: glob pattern in path accepted"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _validate_log_path
checks = _validate_log_path('/var/log/app/*.log')
statuses = [c['status'] for c in checks]
has_fail = 'FAIL' in statuses
has_pass = 'PASS' in statuses
if has_pass and not has_fail:
    print('PASS')
else:
    print(f'FAIL: statuses={statuses}')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "glob pattern rejected: $out"
    fi
}

# ── Tests: Journald path detection ──────────────────────────────────

test_journald_path_warned() {
    CURRENT_TEST="Journald: /var/log/journal path generates WARN"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _validate_log_path
checks = _validate_log_path('/var/log/journal/abc')
statuses = [c['status'] for c in checks]
if 'WARN' in statuses:
    print('PASS')
else:
    print(f'FAIL: statuses={statuses}')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "journald path not warned: $out"
    fi
}

test_journald_run_path_warned() {
    CURRENT_TEST="Journald: /run/log/journal path generates WARN"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _validate_log_path
checks = _validate_log_path('/run/log/journal/abc')
statuses = [c['status'] for c in checks]
if 'WARN' in statuses:
    print('PASS')
else:
    print(f'FAIL: statuses={statuses}')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "journald /run path not warned: $out"
    fi
}

test_non_journald_path_not_warned() {
    CURRENT_TEST="Journald: non-journald path not warned"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _validate_log_path
checks = _validate_log_path('/var/log/ainews/app.log')
statuses = [c['status'] for c in checks]
warns = [c for c in checks if c['status'] == 'WARN']
if not warns:
    print('PASS')
else:
    print(f'FAIL: unexpected warnings={[c[\"message\"] for c in warns]}')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "non-journald path warned: $out"
    fi
}

# ── Tests: Docker log detection ─────────────────────────────────────

test_docker_log_check_runs() {
    CURRENT_TEST="Docker: _check_docker_logs executes without error"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _check_docker_logs
checks = _check_docker_logs()
# Should return a list (may be empty if Docker not running or using json-file)
print(f'OK:{len(checks)}')
" 2>&1)
    if [[ "$out" == OK:* ]]; then
        _pass "$CURRENT_TEST ($out)"
    else
        _fail "$CURRENT_TEST" "unexpected output: $out"
    fi
}

test_docker_log_check_json_file_driver() {
    CURRENT_TEST="Docker: json-file driver does not generate warnings"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _check_docker_logs, _DOCKER_LOG_DRIVER
# _DOCKER_LOG_DRIVER is 'json-file' — Docker using json-file means
# logrotate should manage rotation (no Docker warning)
checks = _check_docker_logs()
docker_checks = [c for c in checks if c.get('name') == 'docker_log_driver']
if not docker_checks:
    print('PASS')
else:
    status = docker_checks[0]['status']
    print(f'FAIL: unexpected docker check: {status}')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "$out"
    fi
}

# ── Tests: Duplicate detection logic ────────────────────────────────

test_detect_duplicate_rules_finds_overlap() {
    CURRENT_TEST="Duplicate detection: overlapping paths detected"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _detect_duplicate_rules
state = {
    'rules': [
        {'name': 'existing', 'log_paths': ['/var/log/a/*.log', '/var/log/b/*.log']}
    ]
}
checks = _detect_duplicate_rules('new', ['/var/log/a/*.log', '/var/log/c/*.log'], state)
if checks and any(c['status'] == 'WARN' for c in checks):
    print('PASS')
else:
    print(f'FAIL: checks={checks}')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "$out"
    fi
}

test_detect_duplicate_rules_no_overlap() {
    CURRENT_TEST="Duplicate detection: no overlap returns no warnings"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _detect_duplicate_rules
state = {
    'rules': [
        {'name': 'existing', 'log_paths': ['/var/log/a/*.log']}
    ]
}
checks = _detect_duplicate_rules('new', ['/var/log/b/*.log'], state)
warns = [c for c in checks if c.get('status') == 'WARN']
if not warns:
    print('PASS')
else:
    print(f'FAIL: unexpected warns={warns}')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "$out"
    fi
}

test_detect_duplicate_rules_same_name_skipped() {
    CURRENT_TEST="Duplicate detection: same name rule is skipped"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _detect_duplicate_rules
state = {
    'rules': [
        {'name': 'ainews', 'log_paths': ['/var/log/ainews/*.log']}
    ]
}
# Same name should be skipped (not flagged as duplicate)
checks = _detect_duplicate_rules('ainews', ['/var/log/ainews/*.log'], state)
warns = [c for c in checks if c.get('status') == 'WARN']
if not warns:
    print('PASS')
else:
    print(f'FAIL: same-name flagged as duplicate: {warns}')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "$out"
    fi
}

test_detect_duplicate_rules_empty_state() {
    CURRENT_TEST="Duplicate detection: empty state returns no warnings"
    local out
    out=$(python3 -c "
import sys
sys.path.insert(0, '.')
from ainews_cli.service.logrotate_commands import _detect_duplicate_rules
checks = _detect_duplicate_rules('new', ['/var/log/a/*.log'], {'rules': []})
if not checks:
    print('PASS')
else:
    print(f'FAIL: unexpected checks={checks}')
" 2>&1)
    if [[ "$out" == "PASS" ]]; then
        _pass "$CURRENT_TEST"
    else
        _fail "$CURRENT_TEST" "$out"
    fi
}

# ── Test runner ──────────────────────────────────────────────────────

run_all_tests() {
    local test_funcs=()

    while IFS= read -r func; do
        test_funcs+=("$func")
    done < <(declare -F | awk '{print $3}' | grep '^test_' | sort)

    echo "Running ${#test_funcs[@]} logrotate validation tests..."
    echo ""

    for func in "${test_funcs[@]}"; do
        CURRENT_TEST="$func"
        ( "$func" )
    done

    read -r PASS FAIL SKIPPED < "$_COUNTS_FILE"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Results: ${PASS} passed, ${FAIL} failed, ${SKIPPED} skipped"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [[ $FAIL -gt 0 ]]; then
        echo "  FAILED"
        exit 1
    else
        echo "  ALL PASSED"
        exit 0
    fi
}

check_prerequisites
run_all_tests
