"""The `asks` request (setting_asks.py): agents asking for more space, the owner's answer, the
settings history and the Agents option, all in one request with an `action`:

- `read` (default): `history` rows of the settings history.
- `ask`: `value`, `reason`, optional `node`, `setting` (`max_size`), `project`, `job_id`,
  `client`; the reply adds `ask`, the stored request, with `state` "waiting" or "applied".
- `answer`: `approve` (bool), optional `node`, `setting`, `value` (another than asked), `note`.
- `undo`: `change`, an id from the settings history.
- `agents`: `option`, "ask" or "allow".

`by` names who answered, for the history: "the dashboard, from <address>" from the dashboard,
else the command and dev machine. Replied `asks_ok`: `asks` (waiting), `changes`, `agents`.
"""

from __future__ import annotations

from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import setting_asks
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest

ACTIONS = ("read", "ask", "answer", "undo", "agents")


def control(req: Request) -> Message:
    action = v.text(req.body, "action", "read")
    if action not in ACTIONS:
        raise BadRequest(f"action: one of {', '.join(ACTIONS)}")
    history = v.integer(req.body, "history", 50, 1, 500)
    by = (v.text(req.body, "by", None) or "a command")[:200]
    extra = {}
    if action == "read":
        with req.store.read() as conn:
            return req.reply(MessageType.ASKS_OK, setting_asks.body(conn, history))
    with req.store.write() as conn:
        if action == "ask":
            extra["ask"] = setting_asks.ask(conn, req.body, req.now)
        elif action == "answer":
            extra["change_id"] = setting_asks.answer(
                conn, v.text(req.body, "node", None), v.text(req.body, "setting", "max_size"),
                v.flag(req.body, "approve"), v.text(req.body, "value", None),
                (v.text(req.body, "note", None) or None), by, req.now)
        elif action == "undo":
            extra["change_id"] = setting_asks.undo(conn, v.text(req.body, "change"), by, req.now)
        else:
            setting_asks.set_option(conn, v.text(req.body, "option"), by, req.now)
        return req.reply(MessageType.ASKS_OK, {**setting_asks.body(conn, history), **extra})
