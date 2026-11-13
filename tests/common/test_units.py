"""Sizes and rates as shown: decimal SI units, one decimal above B (the user's call, 2026-11-13)."""

from mulebox.common import units


def test_sizes_are_decimal_with_one_decimal_above_bytes():
    assert units.size(0) == "0 B"
    assert units.size(999) == "999 B"
    assert units.size(1_500) == "1.5 KB"
    assert units.size(1024) == "1.0 KB"
    assert units.size(41_040_441) == "41.0 MB"
    assert units.size(906_400_000) == "906.4 MB"
    assert units.size(999_960) == "1.0 MB"  # never "1000.0 KB"
    assert units.size(215 * 1000**3) == "215.0 GB"
    assert units.size(3 * 1000**5) == "3000.0 TB"


def test_rates_and_kib_fields():
    assert units.rate(614_000) == "614.0 KB/s"
    assert units.rate_kib(2.0) == "2.0 KB/s"  # 2048 bytes
    assert units.rate_kib(152.7) == "156.4 KB/s"
