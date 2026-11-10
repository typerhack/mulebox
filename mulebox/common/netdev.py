"""The machine's own network traffic: bytes in and out of its physical interfaces (Wi-Fi,
Ethernet), from `/sys/class/net`. Virtual interfaces are left out on purpose: a VPN tunnel's
traffic also crosses Wi-Fi, and a container's crosses a veth and a bridge before it leaves the
machine, so counting them would count the same bytes two or three times (M14.2). Without
`/sys/class/net` (macOS) nothing is read and nothing fails."""

from __future__ import annotations

from pathlib import Path

SYS_NET = Path("/sys/class/net")


def physical(root: Path = SYS_NET) -> list[Path]:
    """The interfaces backed by a device: their link does not resolve under `.../virtual/`."""
    try:
        links = sorted(root.iterdir())
    except OSError:
        return []
    out = []
    for link in links:
        try:
            parts = link.resolve().parts
        except OSError:
            continue
        if "virtual" not in parts:
            out.append(link)
    return out


def _counter(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def totals(root: Path = SYS_NET) -> tuple[int, int] | None:
    """Received and sent bytes over every physical interface; None if none could be read."""
    rx = tx = 0
    found = False
    for link in physical(root):
        got_rx = _counter(link / "statistics" / "rx_bytes")
        got_tx = _counter(link / "statistics" / "tx_bytes")
        if got_rx is None or got_tx is None:
            continue
        rx, tx, found = rx + got_rx, tx + got_tx, True
    return (rx, tx) if found else None


def rates(before: tuple[int, int] | None, after: tuple[int, int] | None,
          span_s: float) -> tuple[float, float] | None:
    """KiB/s in and out between two `totals`; None without both or a time between them. A
    counter that went down (an interface gone or reset) counts as no traffic, not a negative."""
    if before is None or after is None or span_s <= 0:
        return None
    return tuple(round(max(0, b - a) / 1024.0 / span_s, 1)  # type: ignore[return-value]
                 for a, b in zip(before, after))
