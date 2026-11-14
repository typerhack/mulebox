"""Project orders on this node: `project reset` and `clean` for every node (M25.4).

The coordinator sends them with a claim's or heartbeat's reply (`orders`,
coordinator/project_orders.py). Each runs in a thread of its own, so the loop keeps tending
jobs, and what it printed goes back as `order_done` once it ends. While one runs the node claims
no job, so none starts in a folder being removed; a clean skips the branches this node runs a
job in now. Split from agent.py: `Agent` provides `node`, `paths`, `active` and `_call`.
"""

from __future__ import annotations

import threading
from typing import Any

from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.common.protocol import MessageType
from mulebox.worker import project_home, project_work
from mulebox.worker.link import LinkError, request

LOG = get_logger("worker.orders")


def run(order: dict[str, Any], node: Any, paths: Any, skip: set[tuple[str, str]]
        ) -> tuple[int, str]:
    """(exit code, what it printed) of one order."""
    lines: list[str] = []
    try:
        if order.get("action") == "reset":
            project_work.reset(node, paths, str(order["project"]), order.get("branch"),
                               bool(order.get("caches")), bool(order.get("yes")), lines.append)
        elif order.get("action") == "clean":
            used = {project: {branch or None: float(when) for branch, when in seen.items()}
                    for project, seen in (order.get("used") or {}).items()}
            project_work.clean(node, paths, used, int(order.get("days", 14)),
                               bool(order.get("yes")), lines.append, skip)
        else:
            return 2, f"mulebox: this node does not know the order {order.get('action')!r}"
    except (MuleboxError, OSError, KeyError, ValueError, TypeError) as exc:
        lines.append(f"mulebox: {exc}")
        return 2, "\n".join(lines)
    return 0, "\n".join(lines)


class Ordering:
    def _order_state(self) -> dict[str, Any]:
        if not hasattr(self, "_orders"):
            self._orders = {"seen": set(), "running": {}, "done": []}
        return self._orders

    def _take_orders(self, body: dict[str, Any]) -> None:
        state = self._order_state()
        for order in body.get("orders") or ():
            order_id = order.get("order_id") if isinstance(order, dict) else None
            if not isinstance(order_id, str) or order_id in state["seen"]:
                continue
            state["seen"].add(order_id)
            skip = {(job.project, project_home.slug(job.branch)) for job in self.active.values()}
            LOG.info("project order %s: %s", order_id, order.get("action"))

            def work(order=order, order_id=order_id, skip=skip) -> None:
                code, output = run(order, self.node, self.paths, skip)
                state["done"].append((order_id, code, output))
                state["running"].pop(order_id, None)
            state["running"][order_id] = threading.Thread(target=work, daemon=True)
            state["running"][order_id].start()

    def _ordering(self, now: float) -> bool:
        """Report the orders that ended; True while one still runs (claim no job then)."""
        state = self._order_state()
        while state["done"]:
            order_id, code, output = state["done"][0]
            try:
                self._call(request(MessageType.ORDER_DONE, order_id=order_id, exit_code=code,
                                   output=output), now)
            except LinkError:
                break  # told on a later step
            state["done"].pop(0)
        return bool(state["running"])
