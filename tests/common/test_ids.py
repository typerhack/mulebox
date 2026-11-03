from datetime import UTC, datetime, timedelta

import pytest

from mulebox.common import ids
from mulebox.common.ids import CROCKFORD_ALPHABET, id_timestamp, is_valid_id, new_id, new_ulid

PREFIXES = ["job", "att", "wrk", "sub", "req"]


@pytest.mark.parametrize("prefix", PREFIXES)
def test_new_id_has_prefix_and_26_char_ulid(prefix):
    value = new_id(prefix)
    head, _, ulid = value.partition("-")
    assert head == prefix
    assert len(ulid) == 26
    assert set(ulid) <= set(CROCKFORD_ALPHABET)
    assert is_valid_id(value, prefix)


def test_ids_are_unique():
    assert len({new_id("job") for _ in range(2000)}) == 2000


def test_timestamp_round_trips_to_the_millisecond():
    before = datetime.now(UTC) - timedelta(milliseconds=1)
    stamp = id_timestamp(new_id("job"))
    after = datetime.now(UTC) + timedelta(milliseconds=1)
    assert stamp.tzinfo is UTC
    assert before <= stamp <= after


def test_known_timestamp_encoding():
    moment = datetime(2026, 11, 3, 12, 0, 0, 123000, tzinfo=UTC)
    ms = int(moment.timestamp() * 1000)
    assert id_timestamp(f"job-{new_ulid(ms)}") == moment


def test_zero_and_max_timestamps():
    assert new_ulid(0).startswith("0000000000")
    assert new_ulid((1 << 48) - 1).startswith("7ZZZZZZZZZ")
    with pytest.raises(ValueError):
        new_ulid(1 << 48)
    with pytest.raises(ValueError):
        new_ulid(-1)


def test_ids_sort_by_time():
    earlier = f"job-{new_ulid(1_700_000_000_000)}"
    later = f"job-{new_ulid(1_700_000_000_001)}"
    much_later = f"job-{new_ulid(1_800_000_000_000)}"
    assert sorted([much_later, later, earlier]) == [earlier, later, much_later]


def test_new_id_uses_current_time(monkeypatch):
    monkeypatch.setattr(ids.time, "time_ns", lambda: 1_700_000_000_000 * 1_000_000)
    stamp = id_timestamp(new_id("req"))
    assert stamp == datetime.fromtimestamp(1_700_000_000, tz=UTC)


def test_random_part_comes_from_secrets(monkeypatch):
    monkeypatch.setattr(ids.secrets, "randbits", lambda bits: 0)
    assert new_ulid(0) == "0" * 26
    monkeypatch.setattr(ids.secrets, "randbits", lambda bits: (1 << bits) - 1)
    assert new_ulid(0) == "0" * 10 + "Z" * 16


@pytest.mark.parametrize("prefix", ["", "Job", "job-x", "1job", "jo b", "jöb"])
def test_new_id_rejects_bad_prefix(prefix):
    with pytest.raises(ValueError):
        new_id(prefix)


def test_is_valid_id_prefix_filter():
    value = new_id("job")
    assert is_valid_id(value)
    assert is_valid_id(value, "job")
    assert not is_valid_id(value, "att")


GOOD = "01JC3X" + "0" * 19 + "A"  # 26 chars


@pytest.mark.parametrize(
    "value",
    [
        "",
        "job",
        "job-",
        f"-{GOOD}",
        f"job{GOOD}",
        f"job-{GOOD[:-1]}",  # 25 chars
        f"job-{GOOD}0",  # 27 chars
        f"job-{GOOD.lower()}",
        f"job-{GOOD[:-2]}IL",  # I and L are not Crockford
        f"job-8{GOOD[1:]}",  # overflows 128 bits
        f"JOB-{GOOD}",
        f"job-x-{GOOD}",
        f" job-{GOOD}",
        f"job-{GOOD}\n",
    ],
)
def test_is_valid_id_rejects_malformed(value):
    assert len(GOOD) == 26 and is_valid_id(f"job-{GOOD}")
    assert not is_valid_id(value)


def test_is_valid_id_rejects_non_strings():
    assert not is_valid_id(None)  # type: ignore[arg-type]
    assert not is_valid_id(12345)  # type: ignore[arg-type]


def test_id_timestamp_rejects_malformed():
    with pytest.raises(ValueError):
        id_timestamp("job-not-a-ulid")


def test_id_timestamp_beyond_datetime_range():
    with pytest.raises(ValueError):
        id_timestamp(f"job-{new_ulid((1 << 48) - 1)}")
