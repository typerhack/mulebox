"""The `[dashboard]` table and the remotely editable settings of node.toml, for config.py.

Split out of config.py to keep each file small; the rules of each field are in config.py's
docstring, and those of `slots` and `priority` in node_settings.py.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from mulebox.common import node_settings
from mulebox.common.config_reader import Reader

DASHBOARD_MODES = ("off", "local", "lan")
DEFAULT_DASHBOARD_PORT = 8090


def slots(reader: Reader) -> int:
    return reader.integer("slots", 1, node_settings.MIN_SLOTS)  # no top: a big machine may want more


def priority(reader: Reader) -> str:
    value = reader.text("priority", node_settings.DEFAULT_PRIORITY)
    if value not in node_settings.PRIORITIES:
        reader.fail("priority", f"must be one of {', '.join(node_settings.PRIORITIES)}, "
                    f"got {value!r}")
    return value


def dashboard(reader: Reader) -> dict[str, Any]:
    sub = reader.table("dashboard")
    mode = sub.text("mode", "local")
    if mode not in DASHBOARD_MODES:
        sub.fail("mode", f"must be one of {', '.join(DASHBOARD_MODES)}, got {mode!r}")
    port = sub.integer("port", DEFAULT_DASHBOARD_PORT, 1, 65535)
    lan_range = sub.text("lan_range", None)
    lan_address = sub.text("lan_address", None)
    lan_port = sub.integer("lan_port", port, 1, 65535)
    lan_tls = sub.boolean("lan_tls", False)
    lan_password = sub.boolean("lan_password", True)
    controls = sub.boolean("controls", True)
    sub.boolean("cancel_button", False)  # before 0.87.0; the controls replaced it
    if lan_range is not None:
        if "/" not in lan_range:
            hint = f"needs a prefix length, e.g. 192.168.1.0/24, got {lan_range!r}"
            sub.fail("lan_range", hint)
        try:
            lan_range = str(ipaddress.ip_network(lan_range, strict=True))
        except ValueError as exc:
            sub.fail("lan_range", f"must be a network in CIDR form: {exc}")
        if not ipaddress.ip_network(lan_range).is_private:
            sub.fail("lan_range", f"must be a private network, got {lan_range!r}")
    elif mode == "lan":
        sub.fail("lan_range", "is required when mode is 'lan'")
    if lan_address is not None:
        lan_address = _lan_address(sub, lan_address, lan_range)
    elif mode == "lan":
        sub.fail("lan_address", "is required when mode is 'lan'")
    sub.finish()
    return {"mode": mode, "port": port, "lan_range": lan_range, "lan_address": lan_address,
            "lan_port": lan_port, "lan_tls": lan_tls, "lan_password": lan_password,
            "controls": controls}


def _lan_address(sub, text: str, lan_range: str | None) -> str:
    """This machine's address on the LAN: one IPv4 address, inside `lan_range`."""
    try:
        address = ipaddress.IPv4Address(text)
    except ValueError:
        sub.fail("lan_address", f"must be an IPv4 address, got {text!r}")
    if lan_range is None:
        sub.fail("lan_range", "is required when lan_address is set")
    network = ipaddress.ip_network(lan_range)
    if network.version != 4 or address not in network:
        sub.fail("lan_address", f"{text} is not inside lan_range {lan_range}")
    if address.is_unspecified or address.is_loopback:
        # The sign-in applies by the listener's address: on these it would not apply at all.
        sub.fail("lan_address", f"must be this machine's address on the LAN, got {text}")
    return str(address)
