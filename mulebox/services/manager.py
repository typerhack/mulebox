"""The service manager of the machine this runs on."""

from __future__ import annotations

import sys

from mulebox.services.base import Manager, ServiceError


def for_platform(platform: str = sys.platform) -> Manager:
    if platform.startswith("linux"):
        from mulebox.services.systemd import SystemdServices

        return SystemdServices()
    if platform == "darwin":
        from mulebox.services.launchd import LaunchdServices

        return LaunchdServices()
    raise ServiceError(f"mulebox services run on Linux or macOS, not {platform}")
