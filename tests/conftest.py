"""For every test, with `MULEBOX_SERVICE` unset: the Xcode and simulators of the machine the suite runs on are not seen
(worker/xcode.py), so a Mac with Xcode, such as GitHub's, gives the same results as Linux, and
no worker made in a test lists or removes the machine's own simulators. Tests of xcode.py pass
their own folders."""

import pytest

from mulebox.coordinator import store
from mulebox.worker import xcode


@pytest.fixture(autouse=True)
def stores_without_disk_syncs(monkeypatch):
    """A synced commit costs about 6 ms on a node's disk, which tripled the suite's time; what the
    tests check does not rest on it (test_store_durability.py checks the real setting)."""
    monkeypatch.setattr(store, "SYNCHRONOUS", "NORMAL")


@pytest.fixture(autouse=True)
def no_xcode_of_this_machine(monkeypatch, tmp_path_factory):
    monkeypatch.setattr(xcode, "APPLICATIONS", tmp_path_factory.getbasetemp() / "no-applications")
    monkeypatch.setattr(xcode, "SELECTED", lambda: None)
    monkeypatch.setattr(xcode, "_INVENTORY", xcode.Inventory(ask=dict, start=lambda work: work()))
    monkeypatch.setattr(xcode, "simulators", lambda platform=None: None)


@pytest.fixture(autouse=True)
def not_a_mulebox_service(monkeypatch):
    """The suite run under a Mac node's worker does not start its fake ssh disclaimed
    (common/disclaim.py); the worker leaves the marker out of a job's environment too."""
    monkeypatch.delenv("MULEBOX_SERVICE", raising=False)
