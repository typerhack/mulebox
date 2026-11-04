"""Typed keys for what the dashboard app holds (shared by server.py and streams.py)."""

from collections.abc import Callable

from aiohttp import web

from mulebox.dashboard.data import DashboardData
from mulebox.dashboard.hub import Hub
from mulebox.dashboard.session import LanAccess

HUB = web.AppKey("hub", Hub)
DATA = web.AppKey("data", DashboardData)
CLOCK = web.AppKey("clock", Callable)
ALLOWED_HOSTS = web.AppKey("allowed_hosts", frozenset)
LAN = web.AppKey("lan", LanAccess)
