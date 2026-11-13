"""A job's download reading, from its lines, its CPU and its traffic."""

from mulebox.common.download_watch import STALL_S, DownloadWatch, clean

T0 = 1_000_000.0
KEY = "setup-python-Linux-x64-24.04-Ubuntu-python-3.13.18-pip-e3c887ed"


def received(done, total=9806923):
    return f"Received {done} of {total} ({done / total * 100:.1f}%), 0.1 MBs/sec"


def test_a_cache_restore_reads_done_of_total_with_its_rate_and_name():
    watch = DownloadWatch()
    watch.step("Run actions/setup-python@6d4fd22")
    watch.line(f"Cache hit for: {KEY}", T0)
    watch.line(received(0), T0 + 1)
    watch.line(received(1418315), T0 + 21)
    found = watch.reading(T0 + 22, cpu_pct=0.4)
    assert found == {"what": "cache", "name": "pip cache", "step": "Run actions/setup-python@6d4fd22",
                     "done_bytes": 1418315, "total_bytes": 9806923,
                     "rate_bytes_s": round(1418315 / 20, 1), "as_of_s": 1.0,
                     "net_bytes_s": None, "net_scope": None, "waiting_on_network": True,
                     "quiet_s": 1.0, "stalled": False}


def test_no_byte_for_a_minute_is_a_stall_in_a_live_log():
    watch = DownloadWatch()
    watch.line(f"Cache hit for: {KEY}", T0)
    watch.line(received(0, 41040441), T0 + 1)
    assert watch.reading(T0 + STALL_S - 1)["stalled"] is False
    found = watch.reading(T0 + STALL_S + 5, cpu_pct=1.0)
    assert found["stalled"] is True and found["quiet_s"] == STALL_S + 5
    assert found["done_bytes"] == 0 and found["rate_bytes_s"] is None


def test_a_runners_trailing_lines_count_only_the_span_they_cover():
    """Lines reach the node in 4 KB blocks: the time since the last one proves nothing."""
    watch = DownloadWatch(live=False)
    watch.line(received(1418315), T0)
    watch.line(received(1418315), T0 + 30)
    assert watch.reading(T0 + 600)["stalled"] is False  # 30 s covered, then nothing known
    watch.line(received(1418315), T0 + 90)
    found = watch.reading(T0 + 600)
    assert found["stalled"] is True and found["quiet_s"] == 90.0 and found["as_of_s"] == 510.0


def test_the_jobs_own_traffic_decides_the_stall_when_it_is_measured():
    watch = DownloadWatch(live=False)
    watch.line(received(1418315), T0)
    watch.line(received(1418315), T0 + 300)  # 5 min with no byte, as printed
    found = watch.reading(T0 + 400, cpu_pct=0.2, net_bytes_s=600_000.0, net_scope="job")
    assert found["stalled"] is False and found["quiet_s"] == 0.0
    assert found["net_bytes_s"] == 600_000.0 and found["net_scope"] == "job"
    assert watch.reading(T0 + 450, net_bytes_s=0.0, net_scope="job")["quiet_s"] == 50.0
    assert watch.reading(T0 + 470, net_bytes_s=0.0, net_scope="job")["stalled"] is True


def test_the_machines_traffic_is_shown_and_never_decides():
    watch = DownloadWatch()
    watch.line(received(0), T0)
    found = watch.reading(T0 + 120, net_bytes_s=900_000.0, net_scope="machine")
    assert found["net_scope"] == "machine" and found["stalled"] is True


def test_own_traffic_with_an_idle_cpu_and_no_line_is_a_download_of_the_network():
    watch = DownloadWatch(live=False)
    watch.step("Run actions/setup-node@949feb2")
    assert watch.reading(T0, cpu_pct=80.0, net_bytes_s=600_000.0, net_scope="job") is None
    assert watch.reading(T0, cpu_pct=2.0, net_bytes_s=600_000.0, net_scope="machine") is None
    found = watch.reading(T0, cpu_pct=2.0, net_bytes_s=600_000.0, net_scope="job")
    assert found["what"] == "network" and found["step"] == "Run actions/setup-node@949feb2"
    assert found["done_bytes"] is None and found["waiting_on_network"] is True


def test_a_download_ends_at_its_end_line_its_total_or_a_new_step():
    watch = DownloadWatch()
    watch.line(f"Cache hit for: {KEY}", T0)
    assert watch.reading(T0)["done_bytes"] is None
    watch.line("Cache restored successfully", T0 + 1)
    assert watch.reading(T0 + 1) is None
    watch.line("Downloading next@16.4.3: 48.31 kB/43.60 MB", T0 + 2)
    watch.line("Extracting archive", T0 + 3)  # a tool's end: not this download's
    assert watch.reading(T0 + 3)["name"] == "next@16.4.3"
    watch.line("Downloading next@16.4.3: 43.60 MB/43.60 MB", T0 + 4)
    assert watch.reading(T0 + 4) is None
    watch.line("  Downloading torch-2.5.1-cp312-cp312-manylinux1_x86_64.whl (906.4 MB)", T0 + 5)
    found = watch.reading(T0 + 6)
    assert found["total_bytes"] == 906_400_000 and found["done_bytes"] is None
    assert found["quiet_s"] is None and found["stalled"] is None  # pip says nothing more
    watch.step("command")
    assert watch.reading(T0 + 7) is None


def test_image_layers_come_in_as_bytes():
    watch = DownloadWatch()
    watch.step("images")
    watch.image_bytes(2_097_000, None, T0)
    watch.image_bytes(52_000_000, None, T0 + 10)
    found = watch.reading(T0 + 10)
    assert (found["what"], found["done_bytes"], found["total_bytes"]) == ("image", 52_000_000, None)
    assert found["rate_bytes_s"] == round((52_000_000 - 2_097_000) / 10, 1)


def test_clean_keeps_known_keys_and_types():
    assert clean(None) is None and clean({"done_bytes": 1}) is None
    assert clean({"what": "cache", "done_bytes": 12.0, "stalled": 1, "net_scope": "job",
                  "name": "x" * 500, "other": True}) == {
        "what": "cache", "name": "x" * 200, "step": None, "done_bytes": 12, "total_bytes": None,
        "rate_bytes_s": None, "as_of_s": None, "net_bytes_s": None, "net_scope": "job",
        "waiting_on_network": None, "quiet_s": None, "stalled": None}


def test_any_own_traffic_or_printed_progress_is_no_stall():
    """An isolated runner at 2 KiB/s moves bytes: under any throughput line it is not stalled."""
    watch = DownloadWatch(live=False)
    for second in range(0, 200, 10):
        watch.line(received(2048 * second), T0 + second)
        found = watch.reading(T0 + second, cpu_pct=0.5, net_bytes_s=2048.0, net_scope="job")
    assert found["stalled"] is False and found["quiet_s"] == 0.0
    watch = DownloadWatch()
    watch.line(received(0), T0)
    for second in range(10, 200, 10):  # traffic reads zero, the printed bytes still advance
        watch.line(received(2048 * second), T0 + second)
        found = watch.reading(T0 + second, net_bytes_s=0.0, net_scope="job")
    assert found["stalled"] is False


def test_playwrights_tenths_are_not_a_stall_between_them():
    """1 GiB at 1 MiB/s: a line every 102 s."""
    watch = DownloadWatch()
    watch.line("Downloading Chromium 131.0 (playwright build v1148) from https://cdn.example/c.zip", T0)
    assert watch.reading(T0 + 90)["stalled"] is None  # no interval seen yet: unknown
    watch.line("|■■■■■■■■      |  10% of 1024.0 MiB", T0 + 102)
    assert watch.reading(T0 + 190)["stalled"] is False  # within the interval seen
    watch.line("|■■■■■■■■      |  20% of 1024.0 MiB", T0 + 204)
    assert watch.reading(T0 + 300)["stalled"] is False
    assert watch.reading(T0 + 204 + 3 * 102)["stalled"] is True  # far past every interval seen


def test_a_named_end_ends_only_its_own_download():
    watch = DownloadWatch()
    watch.line("Downloading a@1: 1 MB/10 MB", T0)
    watch.line("Downloading b@1: 1 MB/10 MB", T0 + 1)
    watch.line("Downloading a@1: 10 MB/10 MB, done", T0 + 2)
    assert watch.reading(T0 + 2)["name"] == "b@1"
    watch.line("Downloading torch (700.0MiB)", T0 + 3)
    watch.line(" Downloaded numpy", T0 + 4)
    assert watch.reading(T0 + 4)["name"] == "torch"
    watch.line(" Downloaded torch", T0 + 5)
    assert watch.reading(T0 + 5) is None
    watch.line("  Downloading torch-2.5.1-cp312-cp312-manylinux1_x86_64.whl (906.4 MB)", T0 + 6)
    watch.line(" Downloaded torch", T0 + 7)
    assert watch.reading(T0 + 7) is None


def test_an_image_download_ends_at_its_total_or_when_the_layers_end():
    watch = DownloadWatch()
    watch.step("images")
    watch.image_bytes(100, 100, T0)
    assert watch.reading(T0 + 70) is None
    watch.image_bytes(50, None, T0 + 80)
    watch.image_done()  # every layer downloaded, extraction follows
    assert watch.reading(T0 + 200) is None
