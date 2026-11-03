import json
import logging
import re

import pytest

from mulebox.common import log
from mulebox.common.log import get_logger, setup_logging

TEXT_LINE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ (\w+) (\S+) (.*)")


@pytest.fixture(autouse=True)
def reset_mulebox_logger():
    logger = logging.getLogger("mulebox")
    saved = (list(logger.handlers), logger.level, logger.propagate)
    yield
    log._remove_own_handlers(logger)
    logger.handlers[:] = saved[0]
    logger.setLevel(saved[1])
    logger.propagate = saved[2]


def own_handlers():
    handlers = logging.getLogger("mulebox").handlers
    return [h for h in handlers if getattr(h, log._HANDLER_MARK, False)]


def test_text_format(capsys):
    setup_logging()
    get_logger("mulebox.worker").info("job started")
    line = capsys.readouterr().err.strip()
    match = TEXT_LINE.fullmatch(line)
    assert match, line
    assert match.groups() == ("INFO", "mulebox.worker", "job started")


def test_timestamp_is_utc(capsys, monkeypatch):
    monkeypatch.setattr(logging.time, "time_ns", lambda: 1_793_707_200 * 10**9)
    monkeypatch.setattr(logging.time, "time", lambda: 1_793_707_200.0)
    setup_logging()
    get_logger("worker").warning("disk low")
    assert capsys.readouterr().err.startswith("2026-11-03T12:00:00Z WARNING mulebox.worker")


def test_level_filters_and_is_case_insensitive(capsys):
    setup_logging("warning")
    logger = get_logger("coordinator")
    logger.info("hidden")
    logger.error("shown")
    err = capsys.readouterr().err
    assert "hidden" not in err
    assert "ERROR mulebox.coordinator shown" in err


def test_unknown_level_raises():
    with pytest.raises(ValueError):
        setup_logging("LOUD")


def test_idempotent_no_duplicate_lines(capsys):
    setup_logging()
    setup_logging()
    setup_logging("DEBUG")
    get_logger("client").debug("once")
    assert capsys.readouterr().err.count("once") == 1
    assert len(own_handlers()) == 1


def test_reconfigure_replaces_previous_settings(capsys, tmp_path):
    target = tmp_path / "mulebox.log"
    setup_logging(file=target)
    setup_logging()
    get_logger("worker").info("to stderr")
    assert "to stderr" in capsys.readouterr().err
    assert "to stderr" not in target.read_text(encoding="utf-8")


def test_foreign_handlers_are_kept():
    foreign = logging.NullHandler()
    logging.getLogger("mulebox").addHandler(foreign)
    setup_logging()
    setup_logging()
    assert foreign in logging.getLogger("mulebox").handlers
    logging.getLogger("mulebox").removeHandler(foreign)


def test_json_lines(capsys):
    setup_logging(json_lines=True)
    get_logger("worker").info("claimed %s", "job-1")
    entry = json.loads(capsys.readouterr().err.strip())
    assert entry["level"] == "INFO"
    assert entry["logger"] == "mulebox.worker"
    assert entry["msg"] == "claimed job-1"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", entry["ts"])
    assert "exc" not in entry


def test_json_lines_include_exception(capsys):
    setup_logging(json_lines=True)
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        get_logger("worker").exception("failed")
    entry = json.loads(capsys.readouterr().err.strip())
    assert "RuntimeError: boom" in entry["exc"]


def test_text_includes_exception(capsys):
    setup_logging()
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        get_logger("worker").exception("failed")
    assert "RuntimeError: boom" in capsys.readouterr().err


def test_file_output_appends(tmp_path, capsys):
    target = tmp_path / "mulebox.log"
    target.write_text("existing\n", encoding="utf-8")
    setup_logging(file=target)
    get_logger("worker").info("written")
    for handler in own_handlers():
        handler.flush()
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "existing"
    assert lines[1].endswith("INFO mulebox.worker written")
    assert capsys.readouterr().err == ""


def test_does_not_propagate_to_root(caplog):
    setup_logging()
    with caplog.at_level(logging.INFO):
        get_logger("worker").info("private")
    assert "private" not in caplog.text


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("mulebox", "mulebox"),
        ("mulebox.worker", "mulebox.worker"),
        ("worker", "mulebox.worker"),
        ("coordinator.queue", "mulebox.coordinator.queue"),
        ("muleboxer", "mulebox.muleboxer"),
    ],
)
def test_get_logger_names(name, expected):
    assert get_logger(name).name == expected


def test_get_logger_rejects_empty_name():
    with pytest.raises(ValueError):
        get_logger("")
