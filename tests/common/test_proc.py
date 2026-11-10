

def _proc(tmp_path, busy, total):
    (tmp_path / "stat").write_text(f"cpu  0 0 0 0 0\ncpu0 {busy} 0 0 {total - busy} 0 0 0 0\n"
                                   f"cpu1 {busy} 0 0 {total - busy} 0 0 0 0\n")
    (tmp_path / "meminfo").write_text("MemTotal: 1000 kB\nMemAvailable: 250 kB\n")


def test_host_load_between_samples(tmp_path):
    from mulebox.common.proc import HostLoad
    clock = iter([0.0, 1.0, 5.0]).__next__
    load = HostLoad(tmp_path, min_span_s=2.0, clock=clock, net=tmp_path / "no-net")
    _proc(tmp_path, 0, 100)
    assert load.sample() == {"cpu_pct": None, "cores": 2, "mem_pct": 75.0,
                             "net_in_kib_s": None, "net_out_kib_s": None}
    _proc(tmp_path, 50, 200)
    assert load.sample()["cpu_pct"] is None  # 1 s later: the last answer again
    assert load.sample()["cpu_pct"] == 50.0


def test_host_load_without_proc(tmp_path):
    from mulebox.common.proc import HostLoad
    assert HostLoad(tmp_path / "none", net=tmp_path / "none").sample() == {
        "cpu_pct": None, "cores": None, "mem_pct": None, "net_in_kib_s": None,
        "net_out_kib_s": None}


def test_host_load_network_between_samples(tmp_path):
    from mulebox.common.proc import HostLoad
    from tests.common.test_netdev import fake_sys
    net = fake_sys(tmp_path, {"wlp6s0": (0, 0)}, {"tun0": (0, 0)})
    clock = iter([0.0, 4.0]).__next__
    load = HostLoad(tmp_path / "none", min_span_s=2.0, clock=clock, net=net)
    assert load.sample()["net_in_kib_s"] is None  # one sample: no rate yet
    fake_sys(tmp_path, {"wlp6s0": (8192, 4096)}, {"tun0": (8192, 4096)})
    got = load.sample()
    assert (got["net_in_kib_s"], got["net_out_kib_s"]) == (2.0, 1.0)  # the tunnel not again
