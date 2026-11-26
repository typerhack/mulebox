"""What every request handler gets: the store, the staging files, the time, the limits."""

from dataclasses import dataclass
from typing import Any

from mulebox.common import error_codes
from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator.errors import CoordinatorError
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


def error_message(request_id: str, code: str, message: str, error_code: str | None = None,
                  fix: str | None = None) -> Message:
    """An `error` reply: the wire `code` for every client, and from 1.44 `error_code` and
    `fix` (common/error_codes.py), the wire code's own when the raise named neither."""
    error_code = error_code or error_codes.FROM_WIRE.get(code, "node.internal")
    return Message(MessageType.ERROR, request_id or "unknown", {
        "code": code, "message": message, "error_code": error_code,
        "fix": fix or error_codes.fix_for(error_code)})


def error_reply(request_id: str, exc: CoordinatorError) -> Message:
    return error_message(request_id, exc.code, str(exc), exc.error_code, exc.fix)
