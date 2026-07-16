"""GitHub API interactions for version resolution and artifact download.

Replicates the logic from ``scripts/install.sh`` in Python.
Uses only ``urllib.request`` — no external dependencies.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

REPO_OWNER = "dbowm91"
REPO_NAME = "ainews"
GITHUB_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
MAX_RETRIES = 3
RETRY_DELAY = 2
REQUEST_TIMEOUT = 30


# ── Platform detection ───────────────────────────────────────────────


def detect_platform() -> str:
    """Return platform string like ``linux-x86_64``, ``macos-aarch64``.

    Raises ``RuntimeError`` for unsupported platforms.
    """
    system = platform.system()
    machine = platform.machine()

    if system == "Linux":
        os_name = "linux"
    elif system == "Darwin":
        os_name = "macos"
    else:
        raise RuntimeError(f"Unsupported operating system: {system}")

    if machine in ("x86_64", "amd64"):
        arch = "x86_64"
    elif machine in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        raise RuntimeError(f"Unsupported CPU architecture: {machine}")

    return f"{os_name}-{arch}"


# ── HTTP helpers ─────────────────────────────────────────────────────


def _build_opener() -> urllib.request.OpenerDirector:
    """Build a URL opener with proxy and token support."""
    handlers: list[urllib.request.BaseHandler] = []

    # Proxy support
    proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy_url:
        handlers.append(urllib.request.ProxyHandler({"https": proxy_url, "http": proxy_url}))
        logger.debug("Using proxy: %s", proxy_url)

    return urllib.request.build_opener(*handlers)


def _github_request(url: str) -> dict | list:
    """Make a GET request to the GitHub API with retry logic.

    Returns parsed JSON response.
    """
    opener = _build_opener()
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "ainews-cli"}

    token = os.environ.get("AINEWS_GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
        logger.debug("Using GitHub token for authentication")

    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code == 404:
                raise
            logger.warning(
                "GitHub API request failed (attempt %d/%d): HTTP %d %s",
                attempt,
                MAX_RETRIES,
                exc.code,
                exc.reason,
            )
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning(
                "GitHub API request failed (attempt %d/%d): %s",
                attempt,
                MAX_RETRIES,
                exc,
            )

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    raise RuntimeError(
        f"GitHub API request failed after {MAX_RETRIES} attempts: {last_error}"
    )


def _download_url(url: str, dest: Path, description: str = "file") -> None:
    """Download a URL to a local file with retry logic.

    Logs progress via the logging module.
    """
    opener = _build_opener()
    headers = {"User-Agent": "ainews-cli"}

    token = os.environ.get("AINEWS_GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
                total = resp.headers.get("Content-Length")
                total_int = int(total) if total else None
                downloaded = 0

                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_int:
                            pct = downloaded * 100 // total_int
                            logger.info(
                                "Downloading %s: %d%% (%d / %d bytes)",
                                description,
                                pct,
                                downloaded,
                                total_int,
                            )
                        else:
                            logger.info(
                                "Downloading %s: %d bytes",
                                description,
                                downloaded,
                            )
            logger.info("Downloaded %s to %s", description, dest)
            return
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
            logger.warning(
                "Download failed (attempt %d/%d): %s",
                attempt,
                MAX_RETRIES,
                exc,
            )
            # Clean up partial file on failure
            dest.unlink(missing_ok=True)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)

    raise RuntimeError(
        f"Download failed after {MAX_RETRIES} attempts: {last_error}"
    )


# ── Version resolution ───────────────────────────────────────────────


def resolve_version(
    channel: str,
    version: str | None = None,
    commit: str | None = None,
) -> str:
    """Resolve a version identifier for the given channel.

    Returns a string in one of these formats:
    - ``"tag:vX.Y.Z"`` — for tagged releases
    - ``"commit:SHA"`` — for main branch builds

    Parameters
    ----------
    channel:
        One of ``"stable"``, ``"prerelease"``, ``"main"``.
    version:
        Explicit version tag (e.g. ``"1.4.0"``). Overrides channel lookup.
    commit:
        Explicit commit SHA. Overrides everything.
    """
    if commit:
        return f"commit:{commit}"

    if version:
        # Strip leading 'v' if caller passed "v1.4.0"
        clean = version.lstrip("v")
        return f"tag:v{clean}"

    if channel == "stable":
        logger.info("Resolving latest stable release...")
        data = _github_request(f"{GITHUB_API}/releases/latest")
        tag = data.get("tag_name", "")
        if not tag:
            raise RuntimeError("No stable releases found.")
        return f"tag:{tag}"

    if channel == "prerelease":
        logger.info("Resolving latest prerelease...")
        data = _github_request(f"{GITHUB_API}/releases?per_page=10")
        if not isinstance(data, list):
            raise RuntimeError("Unexpected GitHub API response format.")
        for release in data:
            if release.get("prerelease", False):
                tag = release.get("tag_name", "")
                if tag:
                    return f"tag:{tag}"
        raise RuntimeError("No prereleases found.")

    if channel == "main":
        logger.info("Resolving main branch HEAD...")
        data = _github_request(f"{GITHUB_API}/branches/main")
        sha = data.get("commit", {}).get("sha", "")
        if not sha:
            raise RuntimeError("Could not resolve commit SHA for main branch.")
        return f"commit:{sha}"

    raise ValueError(f"Invalid channel: {channel!r}. Must be: stable, prerelease, or main")


# ── Artifact URL construction ────────────────────────────────────────


def resolve_artifact_url(
    resolved: str, platform: str
) -> tuple[str, str, str]:
    """Resolve the download URL and metadata for an artifact.

    Parameters
    ----------
    resolved:
        Output of :func:`resolve_version` (e.g. ``"tag:v1.4.0"``).
    platform:
        Output of :func:`detect_platform` (e.g. ``"linux-x86_64"``).

    Returns
    -------
    tuple[str, str, str]
        ``(download_url, artifact_name, tag_or_commit)``
    """
    tag = ""
    commit = ""

    if resolved.startswith("commit:"):
        commit = resolved[len("commit:"):]
        short = commit[:8]
        artifact_name = f"ainews-main-{short}-{platform}.tar.gz"
        release_tag = f"main-{short}"
        download_url = f"{GITHUB_API}/releases/tags/{release_tag}"
    elif resolved.startswith("tag:"):
        tag = resolved[len("tag:"):]
        version = tag.lstrip("v")
        artifact_name = f"ainews-{version}-{platform}.tar.gz"
        download_url = f"{GITHUB_API}/releases/tags/{tag}"
        release_tag = tag
    else:
        raise ValueError(f"Invalid resolved version format: {resolved!r}")

    # Fetch release metadata to get asset download URL
    try:
        release_data = _github_request(download_url)
        for asset in release_data.get("assets", []):
            if asset.get("name") == artifact_name:
                asset_url = asset.get("browser_download_url", "")
                if asset_url:
                    tag_or_commit = tag or commit[:8]
                    return asset_url, artifact_name, tag_or_commit
    except (RuntimeError, urllib.error.HTTPError):
        logger.debug("Could not fetch release metadata, using fallback URL")

    # Fallback: direct URL pattern
    fallback_ref = tag or f"main-{commit[:8]}"
    asset_url = (
        f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
        f"/releases/download/{fallback_ref}/{artifact_name}"
    )
    tag_or_commit = tag or commit[:8]
    return asset_url, artifact_name, tag_or_commit


# ── Public download function ─────────────────────────────────────────


def download_file(
    url: str, dest: Path, description: str = "file"
) -> None:
    """Download a file with retry and progress logging.

    Parameters
    ----------
    url:
        The URL to download from.
    dest:
        Local destination path.
    description:
        Human-readable label for log messages.
    """
    logger.info("Downloading %s from %s", description, url)
    _download_url(url, dest, description)


# ── Checksum verification ────────────────────────────────────────────


def verify_checksum(file_path: Path, expected_sha256: str) -> str:
    """Compute and verify SHA-256 checksum of a file.

    Parameters
    ----------
    file_path:
        Path to the file to verify.
    expected_sha256:
        Expected hex-encoded SHA-256 hash.

    Returns
    -------
    str
        The actual hex-encoded SHA-256 hash.

    Raises
    ------
    FileNotFoundError
        If *file_path* does not exist.
    ValueError
        If the computed hash does not match *expected_sha256*.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha256.update(chunk)

    actual = sha256.hexdigest()
    if actual.lower() != expected_sha256.lower():
        raise ValueError(
            f"Checksum mismatch for {file_path.name}: "
            f"expected {expected_sha256}, got {actual}"
        )

    return actual


# ── Release info ─────────────────────────────────────────────────────


def fetch_release_info(channel: str) -> dict:
    """Fetch release metadata from GitHub API.

    Parameters
    ----------
    channel:
        One of ``"stable"``, ``"prerelease"``, ``"main"``.

    Returns
    -------
    dict
        Parsed JSON release metadata.
    """
    if channel == "stable":
        return _github_request(f"{GITHUB_API}/releases/latest")

    if channel == "prerelease":
        releases = _github_request(f"{GITHUB_API}/releases?per_page=10")
        if not isinstance(releases, list):
            raise RuntimeError("Unexpected GitHub API response format.")
        for release in releases:
            if release.get("prerelease", False):
                return release
        raise RuntimeError("No prereleases found.")

    if channel == "main":
        return _github_request(f"{GITHUB_API}/branches/main")

    raise ValueError(f"Invalid channel: {channel!r}. Must be: stable, prerelease, or main")
