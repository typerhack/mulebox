"""What every request handler gets: the store, the staging files, the time, the limits."""

from dataclasses import dataclass
from typing import Any

from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store


@dataclass(frozen=True)
class Request:
    store: Store
    staging: Staging
    msg: Message
    now: float
    cluster_slots: int = 1
    dashboard: dict[str, Any] | None = None  # common/dashboard_address.py, for replies

    @property
    def body(self) -> dict[str, Any]:
        return self.msg.body

    def reply(self, type_: MessageType, body: dict[str, Any]) -> Message:
        """A reply that reuses the request's request_id."""
        return Message(type_, self.msg.request_id, body)


def error_message(request_id: str, code: str, message: str) -> Message:
    return Message(MessageType.ERROR, request_id or "unknown", {"code": code, "message": message})
