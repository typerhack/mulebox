"""The `history` request: finished jobs with the History page's filters, newest first."""

from mulebox.common.protocol import MessageType
from mulebox.coordinator import history_api


def test_history_reply_shape_and_filters(monkeypatch):
    seen = {}

    def page(conn, chosen, before, limit):
        seen.update(chosen=chosen, before=before, limit=limit)
        return {"jobs": [], "next_before": None}

    class Read:
        def __enter__(self):
            return None

        def __exit__(self, *a):
            return False

    class Req:
        body = {"project": "example-app", "result": "failed", "q": "", "limit": 5}
        store = type("S", (), {"read": lambda self: Read()})()

        def reply(self, kind, body):
            return kind, body

    monkeypatch.setattr(history_api, "page", page)
    kind, body = history_api.history(Req())
    assert kind is MessageType.HISTORY_OK and body["jobs"] == []
    assert seen == {"chosen": {"project": "example-app", "result": "failed"}, "before": None,
                    "limit": 5}
