

def _proc(tmp_path, busy, total):
    (tmp_path / "stat").write_text(f"cpu  0 0 0 0 0\ncpu0 {busy} 0 0 {total - busy} 0 0 0 0\n"
                                   f"cpu1 {busy} 0 0 {total - busy} 0 0 0 0\n")
    (tmp_path / "meminfo").write_text("MemTotal: 1000 kB\nMemAvailable: 250 kB\n")


def test_host_load_between_samples(tmp_path):
    from mulebox.common.proc import HostLoad
    clock = iter([0.0, 1.0, 5.0]).__next__
    load = HostLoad(tmp_path, min_span_s=2.0, clock=clock)
    _proc(tmp_path, 0, 100)
    assert load.sample() == {"cpu_pct": None, "cores": 2, "mem_pct": 75.0}
    _proc(tmp_path, 50, 200)
    assert load.sample()["cpu_pct"] is None  # 1 s later: the last answer again
    assert load.sample()["cpu_pct"] == 50.0


def test_host_load_without_proc(tmp_path):
    from mulebox.common.proc import HostLoad
    assert HostLoad(tmp_path / "none").sample() == {"cpu_pct": None, "cores": None,
                                                     "mem_pct": None}
