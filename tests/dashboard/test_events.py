import json

import pytest

from mulebox.dashboard.events import EventBus, count, frame


@pytest.mark.parametrize("text, value", [("0", 0), ("12", 12), ("", None), (None, None),
                                         ("-1", None), ("1.5", None), ("²", None),
                                         ("9" * 5000, None)])
def test_count_accepts_only_plain_digits(text, value):
    assert count(text) == value


def test_frame_is_one_sse_message_without_raw_newlines():
    raw = frame("log", {"data": "a\nb"}, "5").decode()
    assert raw.startswith("id: 5\nevent: log\ndata: ")
    assert raw.endswith("\n\n") and raw.count("\n") == 4
    assert json.loads(raw.split("data: ", 1)[1])["data"] == "a\nb"


def test_since_replays_only_what_was_missed():
    bus = EventBus(epoch="e")
    first = bus.publish("queue", {"n": 1})
    bus.publish("queue", {"n": 2})
    assert [e.data["n"] for e in bus.since(first.id)] == [2]
    assert bus.since(bus.last_id) == []


@pytest.mark.parametrize("last_id", [None, "", "other-1", "e-99", "e-x", "e-²", "nodash"])
def test_since_asks_for_a_snapshot_when_it_cannot_replay(last_id):
    bus = EventBus(epoch="e")
    bus.publish("queue", {})
    assert bus.since(last_id) is None


def test_since_refuses_ids_older_than_the_buffer():
    bus = EventBus(keep=2, epoch="e")
    old = bus.publish("queue", {})
    for _ in range(3):
        bus.publish("queue", {})
    assert bus.since(old.id) is None


def test_slow_viewer_is_dropped_without_affecting_others():
    bus = EventBus(queue_size=2, epoch="e")
    slow, fast = bus.subscribe(), bus.subscribe()
    for n in range(2):
        bus.publish("queue", {"n": n})
        fast.queue.get_nowait()
    bus.publish("queue", {"n": 2})
    assert slow.dropped and bus.drops == 1 and bus.subscriber_count == 1
    assert slow.queue.get_nowait() is None  # its stream ends now
    assert fast.queue.get_nowait().data == {"n": 2}
