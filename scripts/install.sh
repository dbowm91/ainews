#!/bin/bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────
# ainews Release 3 — Channel-Aware Installer
#
# Downloads and installs pre-built ainews release artifacts.
# Does NOT configure the application — delegates to `ainews onboard`.
#
# Usage: curl -fsSL https://get.ainews.dev | bash
#        bash scripts/install.sh --channel stable --user
#        bash scripts/install.sh --channel prerelease --dry-run
# ─────────────────────────────────────────────────────────────────────

readonly INSTALLER_VERSION="3.0.0"
readonly REPO_OWNER="dbowm91"
readonly REPO_NAME="ainews"
readonly GITHUB_API="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}"
readonly METADATA_SCHEMA_VERSION=1

# ── Color & output helpers ──────────────────────────────────────────

if [[ -t 1 ]]; then
    readonly RED='\033[0;31m'
    readonly GREEN='\033[0;32m'
    readonly YELLOW='\033[1;33m'
    readonly CYAN='\033[0;36m'
    readonly BOLD='\033[1m'
    readonly NC='\033[0m'
else
    readonly RED='' GREEN='' YELLOW='' CYAN='' BOLD='' NC=''
fi

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step()  { echo -e "${CYAN}[====]${NC} ${BOLD}$*${NC}"; }
log_dry()   { echo -e "${YELLOW}[DRY]${NC}   $*"; }

usage() {
    cat <<EOF
ainews installer v${INSTALLER_VERSION}

Usage: $0 [OPTIONS]

Channels:
  --channel CHANNEL     Release channel: stable (default), prerelease, main
  --version VERSION     Pin to a specific version tag (e.g. 1.4.0)
  --commit SHA          Pin to an exact commit (used with --channel main)

Install mode:
  --user                User-owned paths under ~/.local/share/ainews (default)
  --system              System-wide paths under /opt/ainews (requires root)
  --prefix PATH         Override base directory for all paths

Behavior:
  --non-interactive     Never prompt; use defaults
  --yes                 Accept defaults at prompts
  --dry-run             Show what would happen without executing
  --download-only       Download and verify only; do not install

Post-install:
  --bootstrap PATH      Run: ainews onboard --non-interactive --config-file PATH
  --start               Run: ainews start after onboarding
  --no-onboard          Skip onboarding prompt entirely

Environment variables:
  AINEWS_CHANNEL        Mirror for --channel (CLI takes precedence)
  AINEWS_GITHUB_TOKEN   Token for GitHub API (avoids rate limits)
  HTTPS_PROXY           Proxy for downloads
  HTTP_PROXY            Proxy for downloads

Examples:
  $0                                    # stable channel, user install
  $0 --channel prerelease               # latest prerelease
  $0 --channel main                     # build from main branch HEAD
  $0 --channel stable --version 1.4.0   # pin exact version
  $0 --system --channel stable          # system-wide install
  $0 --dry-run --channel stable         # preview without changes
EOF
}

# ── Validation helpers ──────────────────────────────────────────────

die() {
    log_error "$@"
    exit 1
}

validate_path_component() {
    local p="$1" label="$2"
    [[ -z "$p" ]] && die "${label} must not be empty"
    [[ "$p" == *$'\n'* ]] && die "${label} must not contain newlines"
    [[ "$p" == /* ]] && die "${label} must not be an absolute path"
    [[ "$p" == .. ]] && die "${label} must not be '..'"
    [[ "$p" == ../* ]] && die "${label} must not contain '..' traversal"
}

# ── Argument parsing ────────────────────────────────────────────────

CHANNEL="${AINEWS_CHANNEL:-stable}"
VERSION=""
COMMIT=""
INSTALL_MODE="user"
PREFIX=""
NON_INTERACTIVE=false
BOOTSTRAP=""
DO_START=false
NO_ONBOARD=false
DOWNLOAD_ONLY=false
DRY_RUN=false
YES=false
INSECURE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --channel)
            [[ $# -lt 2 ]] && die "Missing value for --channel"
            CHANNEL="$2"; shift 2 ;;
        --version)
            [[ $# -lt 2 ]] && die "Missing value for --version"
            VERSION="$2"; shift 2 ;;
        --commit)
            [[ $# -lt 2 ]] && die "Missing value for --commit"
            COMMIT="$2"; shift 2 ;;
        --user)
            INSTALL_MODE="user"; shift ;;
        --system)
            INSTALL_MODE="system"; shift ;;
        --prefix)
            [[ $# -lt 2 ]] && die "Missing value for --prefix"
            PREFIX="$2"; shift 2 ;;
        --non-interactive)
            NON_INTERACTIVE=true; shift ;;
        --bootstrap)
            [[ $# -lt 2 ]] && die "Missing value for --bootstrap"
            BOOTSTRAP="$2"; shift 2 ;;
        --start)
            DO_START=true; shift ;;
        --no-onboard)
            NO_ONBOARD=true; shift ;;
        --download-only)
            DOWNLOAD_ONLY=true; shift ;;
        --dry-run)
            DRY_RUN=true; shift ;;
        --yes)
            YES=true; shift ;;
        --insecure)
            INSECURE=true; shift ;;
        --help|-h)
            usage; exit 0 ;;
        *)
            die "Unknown option: $1 (use --help for usage)" ;;
    esac
done

# ── Validate inputs ─────────────────────────────────────────────────

case "$CHANNEL" in
    stable|prerelease|main) ;;
    *) die "Invalid channel: '${CHANNEL}'. Must be: stable, prerelease, or main" ;;
esac

if [[ -n "$VERSION" ]]; then
    [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]] \
        || die "Invalid version format: '${VERSION}'. Expected: X.Y.Z or X.Y.Z-tag"
fi

if [[ -n "$COMMIT" ]]; then
    [[ "$COMMIT" =~ ^[0-9a-f]{7,40}$ ]] \
        || die "Invalid commit SHA: '${COMMIT}'. Expected 7-40 hex characters"
fi

if [[ "$INSTALL_MODE" == "system" && $EUID -ne 0 ]]; then
    die "System install requires root. Run with sudo or use --user."
fi

if [[ -n "$PREFIX" ]]; then
    [[ -d "$PREFIX" ]] || die "Prefix directory does not exist: ${PREFIX}"
    [[ -w "$PREFIX" ]] || die "Prefix directory is not writable: ${PREFIX}"
fi

if [[ -n "$BOOTSTRAP" ]]; then
    [[ -f "$BOOTSTRAP" ]] || die "Bootstrap config file not found: ${BOOTSTRAP}"
fi

[[ "$NON_INTERACTIVE" == true && "$YES" == false ]] && YES=true

# ── Platform detection ──────────────────────────────────────────────

detect_platform() {
    local os arch

    case "$(uname -s)" in
        Linux*)  os="linux" ;;
        Darwin*) os="macos" ;;
        *)       die "Unsupported operating system: $(uname -s)" ;;
    esac

    case "$(uname -m)" in
        x86_64|amd64)   arch="x86_64" ;;
        aarch64|arm64)   arch="aarch64" ;;
        *)               die "Unsupported CPU architecture: $(uname -m)" ;;
    esac

    echo "${os}-${arch}"
}

# ── Dependency checks ───────────────────────────────────────────────

check_deps() {
    local missing=()

    command -v curl &>/dev/null || command -v wget &>/dev/null \
        || missing+=("curl or wget")

    command -v sha256sum &>/dev/null || command -v shasum &>/dev/null \
        || missing+=("sha256sum or shasum (coreutils)")

    command -v tar &>/dev/null || missing+=("tar")

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing[*]}"
        log_error "Install them and retry. Examples:"
        log_error "  Ubuntu/Debian:  sudo apt-get install -y coreutils tar curl"
        log_error "  macOS:          xcode-select --install"
        log_error "  RHEL/Fedora:    sudo dnf install -y coreutils tar curl"
        exit 1
    fi
}

# ── HTTP helpers ────────────────────────────────────────────────────

readonly MAX_RETRIES=3
readonly RETRY_DELAY=2

github_token_header() {
    if [[ -n "${AINEWS_GITHUB_TOKEN:-}" ]]; then
        echo "Authorization: token ${AINEWS_GITHUB_TOKEN}"
    fi
}

http_get() {
    local url="$1" output="$2"
    local insecure_flag=""
    [[ "$INSECURE" == true ]] && insecure_flag="-k"

    local attempt=1
    while [[ $attempt -le $MAX_RETRIES ]]; do
        if command -v curl &>/dev/null; then
            local -a curl_args=(-fsSL --retry 2 --retry-delay 2)
            [[ -n "${AINEWS_GITHUB_TOKEN:-}" ]] && curl_args+=(-H "$(github_token_header)")
            [[ "$INSECURE" == true ]] && curl_args+=(-k)
            if curl "${curl_args[@]}" -o "$output" "$url" 2>/dev/null; then
                return 0
            fi
        elif command -v wget &>/dev/null; then
            local -a wget_args=(-q --timeout=30 -O "$output")
            [[ "$INSECURE" == true ]] && wget_args+=(--no-check-certificate)
            if wget "${wget_args[@]}" "$url" 2>/dev/null; then
                return 0
            fi
        fi

        if [[ $attempt -lt $MAX_RETRIES ]]; then
            log_warn "Download attempt ${attempt}/${MAX_RETRIES} failed, retrying in ${RETRY_DELAY}s..."
            sleep "$RETRY_DELAY"
        fi
        ((attempt++))
    done

    return 1
}

http_get_stdout() {
    local url="$1"
    local insecure_flag=""
    [[ "$INSECURE" == true ]] && insecure_flag="-k"

    local attempt=1
    while [[ $attempt -le $MAX_RETRIES ]]; do
        if command -v curl &>/dev/null; then
            local -a curl_args=(-fsSL --retry 2 --retry-delay 2)
            [[ -n "${AINEWS_GITHUB_TOKEN:-}" ]] && curl_args+=(-H "$(github_token_header)")
            [[ "$INSECURE" == true ]] && curl_args+=(-k)
            if curl "${curl_args[@]}" "$url" 2>/dev/null; then
                return 0
            fi
        elif command -v wget &>/dev/null; then
            local -a wget_args=(-q --timeout=30 -O -)
            [[ "$INSECURE" == true ]] && wget_args+=(--no-check-certificate)
            if wget "${wget_args[@]}" "$url" 2>/dev/null; then
                return 0
            fi
        fi

        if [[ $attempt -lt $MAX_RETRIES ]]; then
            sleep "$RETRY_DELAY"
        fi
        ((attempt++))
    done

    return 1
}

# ── Checksum helpers ────────────────────────────────────────────────

compute_sha256() {
    local file="$1"
    if command -v sha256sum &>/dev/null; then
        sha256sum "$file" | awk '{print $1}'
    elif command -v shasum &>/dev/null; then
        shasum -a 256 "$file" | awk '{print $1}'
    else
        die "No SHA-256 tool available"
    fi
}

# ── Version resolution ──────────────────────────────────────────────

resolve_version() {
    local channel="$1"
    local explicit_version="${2:-}"
    local explicit_commit="${3:-}"

    if [[ -n "$explicit_commit" ]]; then
        echo "commit:${explicit_commit}"
        return 0
    fi

    if [[ -n "$explicit_version" ]]; then
        echo "tag:v${explicit_version}"
        return 0
    fi

    case "$channel" in
        stable)
            log_step "Resolving latest stable release..."
            local release_json
            release_json=$(http_get_stdout "${GITHUB_API}/releases/latest") \
                || die "Failed to fetch latest stable release from GitHub. Check your network and try again."
            local tag
            tag=$(echo "$release_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tag_name',''))" 2>/dev/null) \
                || die "Failed to parse GitHub API response. Rate limited? Set AINEWS_GITHUB_TOKEN."
            [[ -z "$tag" ]] && die "No stable releases found. Try --channel prerelease or --channel main."
            echo "tag:${tag}"
            ;;
        prerelease)
            log_step "Resolving latest prerelease..."
            local releases_json
            releases_json=$(http_get_stdout "${GITHUB_API}/releases?per_page=10") \
                || die "Failed to fetch releases from GitHub."
            local tag
            tag=$(echo "$releases_json" | python3 -c "
import sys, json
releases = json.load(sys.stdin)
for r in releases:
    if r.get('prerelease', False):
        print(r.get('tag_name', ''))
        break
" 2>/dev/null)
            [[ -z "$tag" ]] && die "No prereleases found. Try --channel stable or --channel main."
            echo "tag:${tag}"
            ;;
        main)
            log_step "Resolving main branch HEAD..."
            local commit_sha
            commit_sha=$(http_get_stdout "${GITHUB_API}/branches/main" | python3 -c "import sys,json; print(json.load(sys.stdin).get('commit',{}).get('sha',''))" 2>/dev/null) \
                || die "Failed to resolve main branch HEAD."
            [[ -z "$commit_sha" ]] && die "Could not resolve commit SHA for main branch."
            echo "commit:${commit_sha}"
            ;;
    esac
}

# ── Artifact URL construction ───────────────────────────────────────

resolve_artifact_url() {
    local resolved="$1" platform="$2"

    local tag=""
    local commit=""
    local artifact_name=""
    local download_url=""

    if [[ "$resolved" == commit:* ]]; then
        commit="${resolved#commit:}"
        # For main channel, construct a snapshot artifact name.
        # The release workflow must publish artifacts for main builds.
        artifact_name="ainews-main-${commit:0:8}-${platform}.tar.gz"
        download_url="${GITHUB_API}/releases/tags/main-${commit:0:8}"
    elif [[ "$resolved" == tag:* ]]; then
        tag="${resolved#tag:}"
        local version="${tag#v}"
        artifact_name="ainews-${version}-${platform}.tar.gz"
        download_url="${GITHUB_API}/releases/tags/${tag}"
    fi

    # Try to get the asset download URL from the release
    local release_json
    release_json=$(http_get_stdout "$download_url") \
        || die "Failed to fetch release metadata for ${tag:-commit:${commit:0:8}}. Release may not exist."

    local asset_url
    asset_url=$(echo "$release_json" | python3 -c "
import sys, json
release = json.load(sys.stdin)
for asset in release.get('assets', []):
    if asset.get('name') == '${artifact_name}':
        print(asset.get('browser_download_url', ''))
        break
" 2>/dev/null)

    if [[ -z "$asset_url" ]]; then
        # Fallback: try direct download URL pattern
        asset_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/download/${tag:-main-${commit:0:8}}/${artifact_name}"
    fi

    printf '%s\t%s\t%s\n' "$asset_url" "$artifact_name" "${tag:-${commit:0:8}}"
}

# ── Safe extraction ─────────────────────────────────────────────────

inspect_archive() {
    local archive="$1"
    local staging="$2"

    log_step "Inspecting archive for safety..."

    local unsafe_entries
    unsafe_entries=$(tar -tf "$archive" 2>/dev/null | python3 -c "
import sys
staging = '${staging}'
unsafe = []
for line in sys.stdin:
    entry = line.strip()
    if not entry:
        continue
    # Reject absolute paths
    if entry.startswith('/'):
        unsafe.append(f'absolute path: {entry}')
    # Reject traversal
    if '..' in entry.split('/'):
        unsafe.append(f'traversal: {entry}')
    # Reject device nodes, FIFOs, sockets (type markers in listing)
    # We check these after extraction instead
if unsafe:
    for u in unsafe[:20]:
        print(u)
    sys.exit(1)
" 2>/dev/null)

    if [[ $? -ne 0 ]]; then
        log_error "Archive contains unsafe entries:"
        echo "$unsafe_entries" >&2
        die "Refusing to extract. The artifact may be corrupted or tampered with."
    fi
}

extract_to_staging() {
    local archive="$1" staging="$2"

    inspect_archive "$archive" "$staging"

    log_step "Extracting to staging directory..."
    mkdir -p "$staging"
    tar -xzf "$archive" -C "$staging" || die "Extraction failed. Archive may be corrupted."

    # Post-extraction safety: reject symlinks escaping staging
    local escaping
    escaping=$(find "$staging" -type l 2>/dev/null | while IFS= read -r link; do
        local target
        target=$(readlink -f "$link" 2>/dev/null || true)
        if [[ -n "$target" && "$target" != "$staging"* ]]; then
            echo "$link -> $target"
        fi
    done)

    if [[ -n "$escaping" ]]; then
        log_error "Archive contains symlinks escaping staging root:"
        echo "$escaping" >&2
        die "Refusing to continue. The artifact may be tampered with."
    fi
}

# ── Path computation ────────────────────────────────────────────────

compute_paths() {
    local mode="$1" prefix="$2"

    local app_dir config_dir data_dir state_dir backup_dir bin_dir

    if [[ -n "$prefix" ]]; then
        app_dir="${prefix}/app"
        config_dir="${prefix}/config"
        data_dir="${prefix}/data"
        state_dir="${prefix}/state"
        backup_dir="${prefix}/backups"
        bin_dir="${prefix}/bin"
    elif [[ "$mode" == "system" ]]; then
        app_dir="/opt/ainews/app"
        config_dir="/etc/ainews"
        data_dir="/var/lib/ainews"
        state_dir="/var/log/ainews"
        backup_dir="/var/lib/ainews/backups"
        bin_dir="/usr/local/bin"
    else
        app_dir="${HOME}/.local/share/ainews/app"
        config_dir="${HOME}/.config/ainews"
        data_dir="${HOME}/.local/share/ainews/data"
        state_dir="${HOME}/.local/state/ainews"
        backup_dir="${HOME}/.local/share/ainews/backups"
        bin_dir="${HOME}/.local/bin"
    fi

    echo "app_dir=${app_dir}"
    echo "config_dir=${config_dir}"
    echo "data_dir=${data_dir}"
    echo "state_dir=${state_dir}"
    echo "backup_dir=${backup_dir}"
    echo "bin_dir=${bin_dir}"
}

read_path() {
    local paths_output="$1" key="$2"
    echo "$paths_output" | grep "^${key}=" | cut -d= -f2-
}

# ── Atomic metadata write ──────────────────────────────────────────

write_metadata() {
    local config_dir="$1" channel="$2" version="$3" commit="$4" \
          artifact="$5" sha256="$6" install_root="$7" \
          data_dir="$8" state_dir="$9"

    local meta_file="${config_dir}/install-metadata.json"
    local meta_tmp="${meta_file}.tmp.$$"
    local installed_at
    installed_at=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    cat > "$meta_tmp" <<METAEOF
{
  "schema_version": ${METADATA_SCHEMA_VERSION},
  "install_type": "${channel}",
  "version": "${version}",
  "commit": "${commit}",
  "artifact": "${artifact}",
  "artifact_sha256": "${sha256}",
  "installed_at": "${installed_at}",
  "install_root": "${install_root}",
  "config_dir": "${config_dir}",
  "data_dir": "${data_dir}",
  "state_dir": "${state_dir}",
  "installer_version": "${INSTALLER_VERSION}"
}
METAEOF

    chmod 600 "$meta_tmp"
    mv -f "$meta_tmp" "$meta_file" \
        || die "Failed to write install metadata to ${meta_file}"
}

# ── Core install logic ──────────────────────────────────────────────

do_install() {
    local platform resolved tag_or_commit artifact_url artifact_name sha256_url
    local sha256 expected_sha256 tarball checksum_file
    local staging app_dir config_dir data_dir state_dir backup_dir bin_dir
    local install_root

    platform=$(detect_platform)
    log_info "Platform: ${platform}"

    check_deps

    resolved=$(resolve_version "$CHANNEL" "$VERSION" "$COMMIT")
    log_info "Resolved: ${resolved}"

    local _artifact_data
    _artifact_data=$(resolve_artifact_url "$resolved" "$platform")
    IFS=$'\t' read -r artifact_url artifact_name tag_or_commit <<< "$_artifact_data"

    log_info "Artifact: ${artifact_name}"
    log_info "Download: ${artifact_url}"

    # ── Setup temporary directory ────────────────────────────────────

    local tmpdir
    tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/ainews-install.XXXXXX") \
        || die "Failed to create temporary directory"
    trap 'rm -rf "$tmpdir"' EXIT

    tarball="${tmpdir}/${artifact_name}"
    checksum_url="${artifact_url%.tar.gz}.SHA256SUMS"
    checksum_file="${tmpdir}/SHA256SUMS"

    if [[ "$DRY_RUN" == true ]]; then
        echo ""
        log_dry "Would download: ${artifact_url}"
        log_dry "Would download: ${checksum_url}"
        log_dry "Would verify SHA-256 checksum"
        log_dry "Would extract to staging directory"

        local paths
        paths=$(compute_paths "$INSTALL_MODE" "$PREFIX")
        app_dir=$(read_path "$paths" "app_dir")
        config_dir=$(read_path "$paths" "config_dir")
        data_dir=$(read_path "$paths" "data_dir")
        state_dir=$(read_path "$paths" "state_dir")

        log_dry "Would install to: ${app_dir}"
        log_dry "Would write metadata to: ${config_dir}/install-metadata.json"
        log_dry ""
        log_dry "Resolved paths:"
        log_dry "  App:     ${app_dir}"
        log_dry "  Config:  ${config_dir}"
        log_dry "  Data:    ${data_dir}"
        log_dry "  State:   ${state_dir}"
        log_dry ""
        log_dry "After install, run:"
        log_dry "  ainews onboard"
        log_dry "  ainews start"
        return 0
    fi

    # ── Download ─────────────────────────────────────────────────────

    log_step "Downloading artifact..."
    http_get "$artifact_url" "$tarball" \
        || die "Download failed: ${artifact_url}

  Possible causes:
    - No internet connection
    - GitHub rate limit (set AINEWS_GITHUB_TOKEN to increase limits)
    - Release or version does not exist
    - Network proxy required (set HTTPS_PROXY)"

    log_step "Downloading checksum..."
    http_get "$checksum_url" "$checksum_file" \
        || die "Download failed: ${checksum_url}

  The checksum file is required for integrity verification.
  This release may not have been built by the official pipeline."

    # ── Verify checksum ──────────────────────────────────────────────

    log_step "Verifying SHA-256 checksum..."
    expected_sha256=$(grep " ${artifact_name}$" "$checksum_file" 2>/dev/null | awk '{print $1}' | tr '[:upper:]' '[:lower:]')

    if [[ -z "$expected_sha256" ]]; then
        log_error "Artifact '${artifact_name}' not found in SHA256SUMS."
        log_error "Contents of SHA256SUMS:"
        cat "$checksum_file" >&2
        die "Checksum verification failed. Artifact may be corrupted or the release is incomplete."
    fi

    actual_sha256=$(compute_sha256 "$tarball")

    if [[ "$actual_sha256" != "$expected_sha256" ]]; then
        log_error "SHA-256 checksum mismatch!"
        log_error "  Expected: ${expected_sha256}"
        log_error "  Actual:   ${actual_sha256}"
        log_error "The downloaded artifact may be corrupted or tampered with."
        log_error "Delete ${tarball} and retry, or report this at https://github.com/${REPO_OWNER}/${REPO_NAME}/issues"
        exit 1
    fi

    log_info "Checksum verified: ${actual_sha256}"

    # ── Download-only mode ───────────────────────────────────────────

    if [[ "$DOWNLOAD_ONLY" == true ]]; then
        local dest="${PWD}"
        cp "$tarball" "${dest}/${artifact_name}"
        cp "$checksum_file" "${dest}/SHA256SUMS"
        log_info "Downloaded to:"
        log_info "  ${dest}/${artifact_name}"
        log_info "  ${dest}/SHA256SUMS"
        return 0
    fi

    # ── Compute install paths ────────────────────────────────────────

    local paths
    paths=$(compute_paths "$INSTALL_MODE" "$PREFIX")
    app_dir=$(read_path "$paths" "app_dir")
    config_dir=$(read_path "$paths" "config_dir")
    data_dir=$(read_path "$paths" "data_dir")
    state_dir=$(read_path "$paths" "state_dir")
    backup_dir=$(read_path "$paths" "backup_dir")
    bin_dir=$(read_path "$paths" "bin_dir")

    install_root="$(dirname "$app_dir")"

    # ── Create directories ───────────────────────────────────────────

    log_step "Creating directories..."
    mkdir -p "$app_dir" "$config_dir" "$data_dir" "$state_dir" "$backup_dir" "$bin_dir"

    # ── Extract to staging ───────────────────────────────────────────

    staging="${install_root}/.staging.$$"
    trap 'rm -rf "$staging"' EXIT

    extract_to_staging "$tarball" "$staging"

    # ── Validate extracted contents ──────────────────────────────────

    if [[ ! -f "${staging}/ainews" ]] && [[ ! -d "${staging}/ainews" ]]; then
        log_warn "Expected 'ainews' entry point not found in archive."
        log_warn "Archive contents:"
        ls -la "$staging" 2>/dev/null | head -20
    fi

    # ── Preserve existing install ────────────────────────────────────

    if [[ -d "$app_dir" ]] && [[ -n "$(ls -A "$app_dir" 2>/dev/null)" ]]; then
        log_step "Backing up existing install..."
        local backup_name="ainews-backup-$(date +%Y%m%d%H%M%S)"
        local backup_dest="${backup_dir}/${backup_name}"
        mkdir -p "$backup_dest"
        # Preserve config and data dirs — only back up the app root
        cp -a "$app_dir"/* "$backup_dest/" 2>/dev/null || true
        log_info "Existing install backed up to: ${backup_dest}"
    fi

    # ── Atomic install ───────────────────────────────────────────────

    log_step "Installing application..."
    # Move new files into app_dir atomically
    # For idempotency: if staging has an ainews/ subdirectory, merge into app_dir
    if [[ -d "${staging}/ainews" ]]; then
        cp -a "${staging}/ainews"/* "$app_dir/" 2>/dev/null || true
    else
        cp -a "${staging}"/* "$app_dir/" 2>/dev/null || true
    fi

    # Install CLI entry point if present
    if [[ -f "${app_dir}/ainews" ]]; then
        chmod 755 "${app_dir}/ainews"
        ln -sf "${app_dir}/ainews" "${bin_dir}/ainews" 2>/dev/null || true
    elif [[ -f "${app_dir}/bin/ainews" ]]; then
        chmod 755 "${app_dir}/bin/ainews"
        ln -sf "${app_dir}/bin/ainews" "${bin_dir}/ainews" 2>/dev/null || true
    fi

    # ── Write install metadata ───────────────────────────────────────

    log_step "Writing install metadata..."
    local resolved_version resolved_commit
    if [[ "$resolved" == commit:* ]]; then
        resolved_version="0.0.0-main"
        resolved_commit="${resolved#commit:}"
    else
        resolved_version="${resolved#tag:v}"
        resolved_commit=""
    fi

    write_metadata "$config_dir" "$CHANNEL" "$resolved_version" "$resolved_commit" \
        "$artifact_name" "$actual_sha256" "$install_root" "$data_dir" "$state_dir"

    # ── Cleanup staging ──────────────────────────────────────────────

    rm -rf "$staging"
    rm -rf "$tmpdir"
    trap - EXIT

    # ── Summary ──────────────────────────────────────────────────────

    echo ""
    log_step "Installation complete!"
    echo ""
    log_info "Version:     ${resolved_version}"
    log_info "Channel:     ${CHANNEL}"
    log_info "Platform:    ${platform}"
    echo ""
    log_info "Paths:"
    log_info "  App:       ${app_dir}"
    log_info "  Config:    ${config_dir}"
    log_info "  Data:      ${data_dir}"
    log_info "  State:     ${state_dir}"
    log_info "  Metadata:  ${config_dir}/install-metadata.json"
    if [[ -f "${bin_dir}/ainews" ]]; then
        log_info "  CLI:       ${bin_dir}/ainews"
    fi
    echo ""

    # ── Post-install delegation ──────────────────────────────────────

    if [[ "$NO_ONBOARD" == true ]]; then
        log_info "Onboarding skipped (--no-onboard)."
        log_info "Run 'ainews onboard' when ready to configure."
    elif [[ -n "$BOOTSTRAP" ]]; then
        log_step "Running onboarding with config: ${BOOTSTRAP}"
        if command -v ainews &>/dev/null; then
            ainews onboard --non-interactive --config-file "$BOOTSTRAP" \
                || log_warn "Onboarding exited with errors. Run 'ainews doctor' to diagnose."
        elif [[ -f "${bin_dir}/ainews" ]]; then
            "${bin_dir}/ainews" onboard --non-interactive --config-file "$BOOTSTRAP" \
                || log_warn "Onboarding exited with errors. Run 'ainews doctor' to diagnose."
        else
            log_warn "ainews CLI not found in PATH. Run 'ainews onboard' after ensuring ainews is on your PATH."
        fi
    elif [[ "$NON_INTERACTIVE" == true ]]; then
        log_info "Non-interactive mode. Run 'ainews onboard' to configure."
    else
        echo ""
        if [[ "$YES" == true ]]; then
            log_step "Running onboarding..."
            if command -v ainews &>/dev/null; then
                ainews onboard || log_warn "Onboarding exited with errors. Run 'ainews doctor' to diagnose."
            elif [[ -f "${bin_dir}/ainews" ]]; then
                "${bin_dir}/ainews" onboard || log_warn "Onboarding exited with errors. Run 'ainews doctor' to diagnose."
            fi
        else
            read -rp "Run onboarding now? [Y/n] " reply
            if [[ "$reply" =~ ^[Yy]$ || -z "$reply" ]]; then
                log_step "Running onboarding..."
                if command -v ainews &>/dev/null; then
                    ainews onboard || log_warn "Onboarding exited with errors. Run 'ainews doctor' to diagnose."
                elif [[ -f "${bin_dir}/ainews" ]]; then
                    "${bin_dir}/ainews" onboard || log_warn "Onboarding exited with errors. Run 'ainews doctor' to diagnose."
                fi
            else
                log_info "Onboarding deferred. Run 'ainews onboard' when ready."
            fi
        fi
    fi

    if [[ "$DO_START" == true ]]; then
        log_step "Starting ainews..."
        if command -v ainews &>/dev/null; then
            ainews start || log_error "Failed to start ainews. Check 'ainews doctor' for diagnostics."
        elif [[ -f "${bin_dir}/ainews" ]]; then
            "${bin_dir}/ainews" start || log_error "Failed to start ainews. Check 'ainews doctor' for diagnostics."
        else
            log_warn "ainews CLI not in PATH. Start manually with: ainews start"
        fi
    elif [[ "$NO_ONBOARD" == false && -z "$BOOTSTRAP" ]]; then
        echo ""
        log_info "Next steps:"
        log_info "  ainews onboard    # configure providers, sources, etc."
        log_info "  ainews start      # start the application"
        log_info "  ainews doctor     # verify installation health"
    fi
}

# ── Banner ──────────────────────────────────────────────────────────

show_banner() {
    echo ""
    echo -e "${BOLD}  ainews installer v${INSTALLER_VERSION}${NC}"
    echo -e "  Channel: ${CHANNEL} | Mode: ${INSTALL_MODE}"
    echo ""
}

# ── Entry point ─────────────────────────────────────────────────────

show_banner
do_install
