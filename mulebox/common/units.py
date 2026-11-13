"""Sizes and rates as a person reads them, in the terminal, the logs and every message.

Decimal SI units, 1000-based, with SI labels: B, KB, MB, GB, TB, and rates as KB/s, MB/s, as
package managers and download tools print them (the user's call, 2026-11-13): pip's 906.4 MB
wheel reads 906.4 MB here too. Whole bytes under 1 KB, one decimal in every unit above.
The dashboard has the same rule in web/src/lib/format.ts (`bytes`, `rate`).

Values that are inputs or internal keep their own units: bytes in the API, `*_kib_s` fields
and limits set in code. Only what is shown goes through here.
"""

from __future__ import annotations

UNITS = ("KB", "MB", "GB", "TB")
KIB = 1024  # the `*_kib_s` fields: converted to bytes before they are shown


def size(n: float) -> str:
    """`999` -> `999 B`, `1500` -> `1.5 KB`, `906_400_000` -> `906.4 MB`."""
    if n < 999.5:
        return f"{max(0, round(n))} B"
    value, unit = n / 1000, 0
    while value >= 999.95 and unit < len(UNITS) - 1:
        value, unit = value / 1000, unit + 1
    return f"{value:.1f} {UNITS[unit]}"


def rate(bytes_per_s: float) -> str:
    """Bytes a second -> `614.0 KB/s`."""
    return f"{size(bytes_per_s)}/s"


def rate_kib(kib_s: float) -> str:
    """A `*_kib_s` reading -> `614.0 KB/s`: the field stays binary, the label decimal."""
    return rate(kib_s * KIB)
