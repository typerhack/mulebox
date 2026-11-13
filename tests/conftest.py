"""For every test, with `MULEBOX_SERVICE` unset: the Xcode and simulators of the machine the suite runs on are not seen
(worker/xcode.py), so a Mac with Xcode, such as GitHub's, gives the same results as Linux, and
no worker made in a test lists or removes the machine's own simulators. Tests of xcode.py pass
their own folders."""

import pytest

from mulebox.worker import xcode


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
