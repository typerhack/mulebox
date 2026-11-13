"""The service manager of the machine this runs on."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from mulebox.services.base import Manager, ServiceError


def for_platform(platform: str = sys.platform) -> Manager:
    if platform.startswith("linux"):
        from mulebox.services.systemd import SystemdServices

        return SystemdServices()
    if platform == "darwin":
        from mulebox.services.launchd import LaunchdServices

        return LaunchdServices()
    raise ServiceError(f"mulebox services run on Linux or macOS, not {platform}")


def service_path(platform: str = sys.platform, environ: Mapping[str, str] = os.environ,
                 home: Path | None = None) -> str:
    """The PATH mulebox's services run with on this machine, so a check made over ssh finds the
    tools a job will find. On a Mac an ssh login reads no profile, so Docker Desktop's and
    Homebrew's folders are missing from it; the launchd agents get them (launchd.search_path)."""
    inherited = environ.get("PATH", "")
    if platform == "darwin":
        from mulebox.services.launchd import search_path

        return search_path(home or Path.home(), inherited)
    return inherited
