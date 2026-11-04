"""The root step of `lan` mode, as text: mulebox itself never runs anything as root.

`mulebox dashboard firewall` prints a script for the operator to read and run. It
installs one nftables table with one purpose: only the configured range reaches the
dashboard's LAN port. The table is separate from ufw, Docker and any VPN client, and
nothing else on the machine changes. A oneshot unit loads it before the network is up,
because a plain /etc/nftables.conf usually starts with `flush ruleset`, which would
remove every other tool's rules.
"""

from __future__ import annotations

TABLE = "mulebox_dashboard"
RULES_PATH = "/etc/mulebox/dashboard-firewall.nft"
UNIT_NAME = "mulebox-dashboard-firewall.service"
UNIT_PATH = f"/etc/systemd/system/{UNIT_NAME}"


def ruleset(lan_range: str, lan_port: int) -> str:
    return f"""#!/usr/sbin/nft -f
# Written by `mulebox dashboard firewall`. Reaching port {lan_port} needs a {lan_range} address.
table inet {TABLE} {{}}
delete table inet {TABLE}
table inet {TABLE} {{
    chain input {{
        type filter hook input priority filter; policy accept;
        iifname "lo" accept
        tcp dport {lan_port} ip saddr != {lan_range} drop
        tcp dport {lan_port} meta nfproto ipv6 drop
    }}
}}
"""


def unit() -> str:
    return f"""[Unit]
Description=mulebox dashboard: limit the LAN port to the configured range
Wants=network-pre.target
Before=network-pre.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f {RULES_PATH}
ExecStop=/usr/sbin/nft delete table inet {TABLE}

[Install]
WantedBy=multi-user.target
"""


def script(lan_range: str, lan_port: int) -> str:
    """A shell script that installs and starts the rule. Safe to run again."""
    return f"""#!/bin/sh
# Installs the mulebox dashboard firewall rule. Read it, then run it as root.
set -eu
command -v nft >/dev/null || {{ echo "nft is needed: install nftables" >&2; exit 1; }}
mkdir -p {RULES_PATH.rsplit('/', 1)[0]}
cat > {RULES_PATH} <<'RULES'
{ruleset(lan_range, lan_port)}RULES
nft -c -f {RULES_PATH}
cat > {UNIT_PATH} <<'UNIT'
{unit()}UNIT
systemctl daemon-reload
systemctl enable {UNIT_NAME}
systemctl restart {UNIT_NAME}
nft list table inet {TABLE}
"""
