"""The machine's network from its physical interfaces only (common/netdev.py, M14.2)."""

from __future__ import annotations

from pathlib import Path

from mulebox.common import netdev


def fake_sys(root: Path, physical: dict, virtual: dict) -> Path:
    """A `/sys` with `class/net/<name>` links into `devices/...`, as the kernel lays it out.
    Each value is (rx_bytes, tx_bytes); calling it again updates the counters."""
    net = root / "class" / "net"
    net.mkdir(parents=True, exist_ok=True)
    for kind, names in (("pci0000:00/net", physical), ("virtual/net", virtual)):
        for name, (rx, tx) in names.items():
            device = root / "devices" / kind / name
            (device / "statistics").mkdir(parents=True, exist_ok=True)
            (device / "statistics" / "rx_bytes").write_text(f"{rx}\n")
            (device / "statistics" / "tx_bytes").write_text(f"{tx}\n")
            link = net / name
            if not link.is_symlink():
                link.symlink_to(device)
    return net


def test_only_physical_interfaces_count(tmp_path):
    net = fake_sys(tmp_path, {"wlp6s0": (1000, 200), "enp3s0": (10, 5)},
                   {"lo": (9999, 9999), "tun0": (800, 150), "docker0": (50, 50),
                    "veth1": (50, 50)})
    assert [link.name for link in netdev.physical(net)] == ["enp3s0", "wlp6s0"]
    assert netdev.totals(net) == (1010, 205)


def test_nothing_to_read(tmp_path):
    assert netdev.physical(tmp_path / "none") == []
    assert netdev.totals(tmp_path / "none") is None
    net = fake_sys(tmp_path, {}, {"lo": (1, 1)})
    assert netdev.totals(net) is None  # only virtual ones: no reading, not zero


def test_unreadable_counter_skips_that_interface(tmp_path):
    net = fake_sys(tmp_path, {"wlp6s0": (100, 10), "enp3s0": (7, 7)}, {})
    (tmp_path / "devices/pci0000:00/net/enp3s0/statistics/rx_bytes").write_text("junk")
    assert netdev.totals(net) == (100, 10)


def test_rates():
    assert netdev.rates((0, 0), (2048, 1024), 2.0) == (1.0, 0.5)
    assert netdev.rates(None, (1, 1), 2.0) is None
    assert netdev.rates((1, 1), (2, 2), 0.0) is None
    assert netdev.rates((5000, 5000), (100, 6024), 1.0) == (0.0, 1.0)  # a reset: no traffic


def test_coordinator_keeps_sane_network_readings():
    from mulebox.coordinator.validate import load
    got = load({"load": {"net_in_kib_s": 12.5, "net_out_kib_s": -1, "cpu_pct": 5}})
    assert got["net_in_kib_s"] == 12.5 and got["net_out_kib_s"] is None
    assert load({"load": {"net_in_kib_s": True}})["net_in_kib_s"] is None


def test_machine_list_shows_rates():
    from mulebox.client.machine_commands import per_second
    assert per_second(None) == "-"
    assert per_second(2.0) == "2.0 KB/s"
    assert per_second(3 * 1024) == "3.1 MB/s"
