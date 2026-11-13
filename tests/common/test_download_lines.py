"""Download lines, in the shapes real tools print them (the cache lines are from the node's own
CI runs of 2026-11-12, over its VPN)."""

import pytest

from mulebox.common import download_lines as dl
from mulebox.common.download_lines import Seen, parse


def test_github_cache_restore_as_setup_python_printed_it():
    key = ("setup-python-Linux-x64-24.04-Ubuntu-python-3.13.18-pip-"
           "e3c887ed8b6342b655f022085ef0b9065f65ee8cc7e6318e7f15eb55737b7dd6")
    assert parse(f"Cache hit for: {key}") == Seen(dl.START, dl.CACHE, "pip cache")
    assert parse("Received 0 of 9806923 (0.0%), 0.0 MBs/sec") == Seen(
        dl.PROGRESS, dl.CACHE, None, 0, 9806923)
    assert parse("Received 1418315 of 9806923 (14.5%), 0.1 MBs/sec") == Seen(
        dl.PROGRESS, dl.CACHE, None, 1418315, 9806923)
    assert parse("Cache Size: ~9 MB (9918658 B)") == Seen(
        dl.PROGRESS, dl.CACHE, None, 9918658, 9918658)
    for end in ("Cache restored successfully",
                f"Cache restored from key: {key}",
                "Cache not found for input keys: node-cache-Linux-x64-npm-dd22",
                "##[warning]Failed to restore: The operation cannot be completed in timeout."):
        assert parse(end) == Seen(dl.END, dl.CACHE)


@pytest.mark.parametrize("key, name", [
    ("node-cache-Linux-x64-npm-dd2265784219c51b685687108913e2fe54ea6d310c96fca082a93e7af45426d5",
     "npm cache"),
    ("node-cache-Linux-x64-pnpm-0123", "pnpm cache"),
    ("Linux-build-cargo-0123", "cache"),
])
def test_a_cache_is_named_after_its_package_manager_when_the_key_says(key, name):
    assert parse(f"Cache hit for restore-key: {key}").name == name


def test_a_tool_into_the_runners_tool_cache_has_a_name_and_no_bytes():
    url = ("https://github.com/actions/python-versions/releases/download/3.13.1-12345/"
           "python-3.13.1-linux-24.04-x64.tar.gz")
    assert parse(f'Download from "{url}"') == Seen(
        dl.START, dl.TOOL, "python-3.13.1-linux-24.04-x64.tar.gz")
    node = ("Acquiring 22.12.0 - x64 from https://github.com/actions/node-versions/releases/"
            "download/22.12.0-1234/node-22.12.0-linux-x64.tar.gz")
    assert parse(node).name == "node-22.12.0-linux-x64.tar.gz"
    for end in ("Extract downloaded archive", "Extracting ...", "Adding to the cache ...",
                "Successfully set up CPython (3.13.1)"):
        assert parse(end) == Seen(dl.END, dl.TOOL)


def test_package_managers():
    assert parse("Downloading next@16.4.3: 48.31 kB/43.60 MB") == Seen(
        dl.PROGRESS, dl.PACKAGE, "next@16.4.3", 48310, 43_600_000)
    assert parse("Downloading next@16.4.3: 43.60 MB/43.60 MB, done") == Seen(
        dl.END, dl.PACKAGE, "next@16.4.3", 43_600_000, 43_600_000)
    pip = "  Downloading torch-2.5.1-cp312-cp312-manylinux1_x86_64.whl (906.4 MB)"
    assert parse(pip) == Seen(dl.START, dl.PACKAGE,
                              "torch-2.5.1-cp312-cp312-manylinux1_x86_64.whl", None, 906_400_000)
    assert parse("Downloading torch (700.0MiB)").total == 700 * 1024 * 1024  # uv
    assert parse(" Downloaded torch").kind == dl.END
    assert parse("Installing collected packages: torch") == Seen(dl.END, dl.PACKAGE)


def test_playwright_without_a_terminal():
    start = ("Downloading Chromium 131.0.6778.33 (playwright build v1148) from "
             "https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1148/"
             "chromium-linux.zip")
    assert parse(start) == Seen(dl.START, dl.BROWSER,
                                "Chromium 131.0.6778.33 (playwright build v1148)")
    step = parse("|■■■■■■■■                                                                        "
                 "|  10% of 164.7 MiB")
    assert step.kind == dl.PROGRESS and step.total == int(164.7 * 1024 * 1024)
    assert step.done == step.total * 10 // 100
    end = ("Chromium 131.0.6778.33 (playwright build v1148) downloaded to "
           "/home/alice/.cache/ms-playwright/chromium-1148")
    assert parse(end) == Seen(dl.END, dl.BROWSER, "Chromium 131.0.6778.33 (playwright build v1148)")


@pytest.mark.parametrize("line", [
    "", "   ", "Run python -m pip install -q -e '.[dev]'", "Received a message",
    "Downloading", "Cache Size: unknown", "........................ [  2%]",
    "Successfully installed mulebox-1.14.1",  # pip's end: not a tool's
])
def test_other_lines_are_nothing_or_no_progress(line):
    seen = parse(line)
    assert seen is None or seen.kind == dl.END


def test_a_name_is_cut():
    assert len(parse(f"Downloading {'x' * 300}.whl (1 MB)").name) == dl.MAX_NAME


@pytest.mark.parametrize("line", [
    "| | 10% of ... MiB", "|■■| 10% of 1.2.3 MiB", f"|■| 50% of {'9' * 400} MiB",
    f"Downloading next@1: {'9' * 400} MB/{'9' * 400} MB", f"Downloading torch ({'9' * 400}.5 GB)",
    f"Received {'9' * 5000} of {'9' * 5000} (1.0%), 0.1 MBs/sec",
    f"Cache Size: ~1 MB ({'9' * 5000} B)", "Downloading x: 1.5.5 MB/2 MB",
])
def test_junk_numbers_never_raise(line):
    seen = parse(line)
    assert seen is None or all(v is None or v < 10**30 for v in (seen.done, seen.total))


def test_size_bytes_refuses_what_is_not_a_finite_size():
    for number, unit in (("1e400", "MB"), ("inf", "GB"), ("nan", "B"), ("9" * 400, "TB")):
        with pytest.raises(ValueError):
            dl.size_bytes(number, unit)


def test_uvs_end_keeps_the_package_name():
    assert parse(" Downloaded torch") == Seen(dl.END, dl.PACKAGE, "torch")
