"""macOS readings from the commands' own text (taken from a real Mac), and the Host facade."""

import sys

import pytest

from mulebox.common import darwin_host, docker_socket, host
from mulebox.common.proc import HostLoad

VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                     8278.
Pages active:                                 469613.
Pages inactive:                               460555.
Pages speculative:                             11779.
Pages wired down:                             149698.
"Translation faults":                      589142086.
"""
NETSTAT = """Name       Mtu   Network       Address            Ipkts Ierrs     Ibytes    Opkts Oerrs     Obytes  Coll
lo0        16384 <Link#1>                      19606442     0 12290770423 19606442     0 12290770423     0
lo0        16384 127           127.0.0.1       19606442     - 12290770423 19606442     - 12290770423     -
en0        1500  <Link#11>   12:f8:a0:ec:ae:71 1000     0       5000      900     0       7000     0
en0        1500  192.168.1     192.168.1.50    1000     -       5000      900     -       7000     -
en1*       1500  <Link#12>   12:f8:a0:ec:ae:72   10     0        100       10     0        200     0
utun3      1380  <Link#20>                       50     0       5000       50     0       5000     0
bridge100  1500  <Link#21>   12:f8:a0:ec:ae:73   50     0       9999       50     0       9999     0
"""


def test_memory_counts_free_inactive_and_speculative_pages_as_available():
    got = darwin_host.parse_vm_stat(VM_STAT, 25769803776)
    available = (8278 + 460555 + 11779) * 16384
    assert got == {"total": 25769803776, "available": available,
                   "used": 25769803776 - available}
    assert darwin_host.parse_vm_stat("no page size here", 100) is None
    assert darwin_host.parse_vm_stat(VM_STAT.replace("Pages free", "x"), 100) is None


def test_swap_usage():
    text = "total = 2048.00M  used = 620.50M  free = 1427.50M  (encrypted)"
    assert darwin_host.parse_swapusage(text) == {"total": 2048 << 20, "used": int(620.5 * (1 << 20))}
    assert darwin_host.parse_swapusage("") is None


def test_network_counts_en_interfaces_only():
    """en0 and a down en1 count; loopback, a VPN tunnel and Docker's bridge do not."""
    assert darwin_host.parse_netstat(NETSTAT) == (5000 + 100, 7000 + 200)
    assert darwin_host.parse_netstat(NETSTAT.split("en0")[0]) is None


def test_the_linux_host_is_unchanged_and_the_mac_one_is_picked_on_a_mac(tmp_path):
    assert isinstance(host.for_platform("linux"), host.LinuxHost)
    assert isinstance(host.for_platform("darwin"), host.DarwinHost)
    (tmp_path / "stat").write_text("cpu  0 0 0 0 0\ncpu0 50 0 0 30 20 0 0 0\n")
    linux = host.LinuxHost(tmp_path, tmp_path / "no-net")
    assert linux.cores() == [(50, 100)] and linux.busy_seconds() == 0.7
    assert linux.memory() is None and linux.net() is None


def test_the_mac_host_turns_ticks_into_busy_and_total(monkeypatch):
    monkeypatch.setattr(darwin_host, "core_ticks", lambda: [[60, 20, 100, 20], [0, 0, 50, 0]])
    mac = host.DarwinHost()
    assert mac.cores() == [(100, 200), (0, 50)]
    assert mac.busy_seconds() == 1.0  # 100 ticks at 100 a second


def test_a_wrapping_tick_counter_does_not_read_as_an_idle_core():
    top = 0xFFFFFFFF
    samples = iter([[[top - 4, 0, 100, 0]], [[5, 0, 110, 0]]])  # user wrapped: 10 busy ticks
    mac = host.DarwinHost(ticks=lambda: next(samples))
    (busy0, total0), (busy1, total1) = mac.cores()[0], mac.cores()[0]
    assert (busy1 - busy0, total1 - total0) == (10, 20)


def test_host_load_reads_through_a_given_host():
    class Fixed:
        def cores(self):
            return [(10, 100), (30, 100)]

        def memory(self):
            return {"total": 100, "available": 25, "used": 75}

        def net(self):
            return (0, 0)

    load = HostLoad(host=Fixed(), clock=iter([0.0, 5.0]).__next__)
    assert load.sample()["mem_pct"] == 75.0 and load.sample()["cores"] == 2


@pytest.mark.skipif(sys.platform != "darwin", reason="the kernel call exists only on macOS")
def test_this_mac_gives_real_readings():
    ticks = darwin_host.core_ticks()
    assert ticks and all(len(core) == darwin_host.CPU_STATES for core in ticks)
    assert darwin_host.memory()["total"] > 0


def test_core_ticks_is_none_off_a_mac(monkeypatch):
    monkeypatch.setattr(darwin_host.sys, "platform", "linux")
    assert darwin_host.core_ticks() is None


def test_the_docker_socket_as_the_docker_command_finds_it(tmp_path):
    present = tmp_path / "docker.sock"
    present.write_text("")
    ask = {"context": lambda: "/Users/alice/.colima/default/docker.sock"}
    assert docker_socket.socket_path({"DOCKER_HOST": "unix:///run/x.sock"}) == "/run/x.sock"
    assert docker_socket.socket_path({"DOCKER_HOST": "tcp://192.168.1.50:2375"}) is None
    assert docker_socket.socket_path({}, default=str(present),
                                     context=lambda: None) == str(present)
    # the chosen context wins over the usual socket, as it does for the docker command
    assert docker_socket.socket_path({}, default=str(present),
                                     context=ask["context"]).endswith("colima/default/docker.sock")
    assert docker_socket.socket_path({}, default=str(tmp_path / "none"),
                                     context=lambda: None) is None
