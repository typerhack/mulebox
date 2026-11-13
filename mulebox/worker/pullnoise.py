"""Image pulls in a job's log: per-layer progress goes, the outcome lines stay.

A slow pull printed thousands of lines per image, which buried the rest of the log. Without a
terminal, Compose 5 prints one line per layer event, and `Downloading` gives what has arrived
of that layer so far with no total:

     9986a736f7d3 Pulling fs layer 0B
     9986a736f7d3 Downloading 2.097MB
     9986a736f7d3 Download complete 0B
     Image memcached:1.6.32-alpine Pulled

Compose 2 prints `Downloading [==>  ]  12.3MB/45.6MB`, and BuildKit `#5 sha256:... 12.3MB /
45.6MB 1.2s`. All three are understood. Lines about images, networks and containers pass, and
so does anything that is not one of these exact shapes, such as an error or a retry.

What remains of the layers is one line saying how much has been downloaded, every
`EVERY_BYTES` while it lasts and after a run of layer lines. It is a lower bound: the last
piece of a layer before `Download complete` is not printed. There is no percentage, because
the size of what is still to come is not known. `--progress json` has a `total` per layer
(Compose 5), but only once a layer has started, and asking for it would break older
versions.

pnpm has the same habit for a large package, `Downloading next@16.4.3: 48.31 kB/43.60 MB`, a line
each time a few KB arrive. Those go too, and its last line, which ends `, done`, stays. They do not
count as image layers.

Text arrives redacted, whole lines at a time (logtail.py), and nothing here changes a line.
"""

from __future__ import annotations

import re

from mulebox.common.download_lines import SIZE as _SIZE, size_bytes as _bytes

EVERY_BYTES = 100_000_000
_LAYER = re.compile(
    r"^\s*(?:[\w.-]+\s+)?([0-9a-f]{12}):?\s+(Pulling fs layer|Waiting|Verifying Checksum|"
    r"Download complete|Downloading|Extracting|Pull complete|Already exists)\b(.*)$")
_BUILD_LAYER = re.compile(
    rf"^#\d+\s+sha256:([0-9a-f]{{12}})[0-9a-f]{{52}}\s+{_SIZE}\s*/\s*{_SIZE}\s+[\d.]+s(?:\s+done)?\s*$")
_BUILD_EXTRACT = re.compile(r"^#\d+\s+extracting\s+sha256:[0-9a-f]{64}\s+[\d.]+s\s*$")
_PACKAGE = re.compile(rf"^Downloading \S+: {_SIZE}\s*/\s*{_SIZE}\s*$")
_LANDED = ("Verifying Checksum", "Download complete", "Extracting", "Pull complete", "Already exists")
_AMOUNT = re.compile(rf"{_SIZE}(?:\s*/\s*{_SIZE})?")


class PullNoise:
    def __init__(self) -> None:
        self._layers: dict[str, int] = {}  # bytes seen per layer
        self._totals: dict[str, int] = {}  # sizes a line gave
        self._pending: set[str] = set()  # layers whose data has yet to arrive
        self._landed: set[str] = set()  # layers whose data is all here
        self._reported = 0  # bytes the tracker knows
        self._said = 0  # bytes the log has been told
        self._next_line = EVERY_BYTES

    @property
    def total(self) -> int:
        return sum(self._layers.values())

    @property
    def size(self) -> int | None:
        """What the layers seen so far weigh, when every one of them gave its size (Compose 2,
        BuildKit); None for Compose 5, which gives none, and before any layer."""
        if not self._layers or any(layer not in self._totals for layer in self._layers):
            return None
        return sum(self._totals.values())

    @property
    def downloading(self) -> bool:
        """A layer is on its way: false once every layer seen has its data (complete, already
        there, or extracting), which a long extraction follows with no byte moving."""
        return bool(self._pending)

    def _state(self, layer: str, landed: bool) -> None:
        if landed:
            self._pending.discard(layer)
            self._landed.add(layer)
        elif layer not in self._landed:
            self._pending.add(layer)

    def take_new_bytes(self) -> int:
        """Bytes downloaded since the last call."""
        fresh, self._reported = self.total - self._reported, self.total
        return fresh

    def _seen(self, layer: str, current: int, size: int | None) -> None:
        self._layers[layer] = max(self._layers.get(layer, 0), current)
        if size is not None:
            self._totals[layer] = size

    def _complete(self, layer: str) -> None:
        if layer in self._totals:
            self._layers[layer] = self._totals[layer]

    def _layer_line(self, text: str) -> bool:
        """True if `text` is progress of a layer; what it says is counted."""
        if _PACKAGE.match(text):
            return True
        built = _BUILD_LAYER.match(text)
        if built:
            self._seen(built[1], _bytes(built[2], built[3]), _bytes(built[4], built[5]))
            done = text.rstrip().endswith("done")
            if done:
                self._complete(built[1])
            self._state(built[1], done)
            return True
        if _BUILD_EXTRACT.match(text):
            return True
        found = _LAYER.match(text)
        if found is None:
            return False
        if found[2] == "Downloading":
            amount = _AMOUNT.search(found[3])
            if amount:
                size = _bytes(amount[3], amount[4]) if amount[3] else None
                self._seen(found[1], _bytes(amount[1], amount[2]), size)
        elif found[2] == "Download complete":
            self._complete(found[1])
        self._state(found[1], found[2] in _LANDED)
        return True

    def _summary(self) -> list[str]:
        if self.total <= self._said:
            return []
        self._said = self.total
        return [f"mulebox: at least {self.total / 1e6:.0f} MB of image layers downloaded\n"]

    def line(self, text: str) -> list[str]:
        """What stays of one line: the line, nothing, or a summary before it."""
        if self._layer_line(text.rstrip("\r\n")):
            if self.total < self._next_line:
                return []
            self._next_line = (self.total // EVERY_BYTES + 1) * EVERY_BYTES
            return self._summary()
        return [*self._summary(), text]

    def flush(self) -> list[str]:
        return self._summary()
