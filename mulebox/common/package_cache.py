"""The package caches a project can ask for, by name.

Client, coordinator and worker all need these names, and nothing else about the caches:
what a cache is on disk lives in worker/caches.py. A project asks for one in `needs`, as it
asks for `playwright`. A worker reports them by itself (common/compose.py), so nobody has to
add them to a config, and an older worker can never claim a job that relies on one.
"""

from __future__ import annotations

PNPM = "cache-pnpm"
COMPOSER = "cache-composer"
NPM = "cache-npm"
PIP = "cache-pip"
CAPABILITIES = (PNPM, COMPOSER, NPM, PIP)
