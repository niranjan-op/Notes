"""In-app update checker and silent Inno Setup installer runner."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

GITHUB_REPO = "niranjan-op/Notes"
_VERSION_PART = re.compile(r"\d+")
_ALLOWED_HOSTS = {"github.com", "api.github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}


@dataclass(frozen=True)
class ReleaseInfo:
    """Metadata for a published GitHub release."""

    version: str
    tag_name: str
    html_url: str
    installer_url: str | None = None
    installer_name: str = ""
    installer_size: int = 0


def parse_version(raw: str) -> tuple[int, ...]:
    """Convert a version string like ``'v1.3.0'`` into a comparable tuple ``(1, 3, 0)``."""
    cleaned = raw.strip().lstrip("vV").split("-", 1)[0]
    parts = [int(match) for match in _VERSION_PART.findall(cleaned)]
    return tuple(parts) if parts else (0,)


def is_newer_version(candidate: str, current: str) -> bool:
    """Return True when ``candidate`` is strictly newer than ``current``."""
    cand_tuple = parse_version(candidate)
    curr_tuple = parse_version(current)
    length = max(len(cand_tuple), len(curr_tuple))
    cand_padded = cand_tuple + (0,) * (length - len(cand_tuple))
    curr_padded = curr_tuple + (0,) * (length - len(curr_tuple))
    return cand_padded > curr_padded


def _is_trusted_https_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host in _ALLOWED_HOSTS or host.endswith(".github.com") or host.endswith(".githubusercontent.com")
    )


def release_from_payload(payload: dict, current_version: str) -> ReleaseInfo | None:
    """Extract a ``ReleaseInfo`` if ``payload`` represents a newer non-draft release."""
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        return None
    tag_name = str(payload.get("tag_name") or "").strip()
    if not tag_name or not is_newer_version(tag_name, current_version):
        return None

    version = tag_name.lstrip("vV") or tag_name
    html_url = str(payload.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/latest")
    assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []

    installer_url: str | None = None
    installer_name = ""
    installer_size = 0
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if name.lower().endswith(".exe") and _is_trusted_https_url(url):
            installer_url = url
            installer_name = name
            installer_size = int(asset.get("size") or 0)
            if "setup" in name.lower():
                break

    return ReleaseInfo(
        version=version,
        tag_name=tag_name,
        html_url=html_url,
        installer_url=installer_url,
        installer_name=installer_name,
        installer_size=installer_size,
    )


def check_for_update(
    current_version: str,
    repo: str = GITHUB_REPO,
    timeout: float = 8.0,
) -> ReleaseInfo | None:
    """Query GitHub Releases and return ``ReleaseInfo`` when a newer version is available."""
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"SecureNotes/{current_version}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise ConnectionError(f"Update check failed (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise ConnectionError("Could not reach GitHub to check for updates.") from exc

    return release_from_payload(payload, current_version)


def download_installer(
    release: ReleaseInfo,
    on_progress: Callable[[int, int], None] | None = None,
    timeout: float = 30.0,
    destination_dir: Path | None = None,
) -> Path:
    """Download the release's Windows setup `.exe` to a temporary file and return its path."""
    if not release.installer_url or not _is_trusted_https_url(release.installer_url):
        raise ValueError("No trusted Windows installer is attached to this release.")

    target_dir = Path(destination_dir) if destination_dir else Path(tempfile.gettempdir())
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_ver = re.sub(r"[^0-9A-Za-z._-]", "_", release.version)
    final_path = target_dir / f"SecureNotes-Setup-{safe_ver}-x64.exe"
    part_path = final_path.with_name(final_path.name + ".part")

    request = urllib.request.Request(
        release.installer_url,
        headers={"User-Agent": f"SecureNotes/{release.version}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            total = int(response.headers.get("Content-Length") or release.installer_size or 0)
            downloaded = 0
            with open(part_path, "wb") as out_file:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if on_progress is not None:
                        on_progress(downloaded, total)
        if downloaded == 0 or (release.installer_size > 0 and downloaded != release.installer_size):
            raise OSError("Downloaded installer is incomplete.")
        os.replace(part_path, final_path)
        return final_path
    except Exception as exc:
        if part_path.exists():
            try:
                part_path.unlink()
            except OSError:
                pass
        if isinstance(exc, (urllib.error.URLError, TimeoutError, OSError)):
            raise ConnectionError("Failed to download the update installer.") from exc
        raise


def launch_windows_installer(installer_path: Path) -> None:
    """Start the Inno Setup installer in silent upgrade mode."""
    installer_path = Path(installer_path)
    if not sys.platform.startswith("win"):
        raise OSError("Silent installer updates are only supported on Windows.")
    if not installer_path.is_file() or installer_path.suffix.lower() != ".exe":
        raise ValueError("Invalid installer executable path.")

    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [
            str(installer_path),
            "/SILENT",
            "/SUPPRESSMSGBOXES",
            "/CLOSEAPPLICATIONS",
            "/NORESTART",
        ],
        close_fds=True,
        creationflags=creationflags,
    )

