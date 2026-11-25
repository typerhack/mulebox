"""The worker's side of a node that rests (design.md, A node that rests; health.py).

Split from agent.py: `Agent` provides the rest (`node`, `paths`, `docker`, `active`, `finishing`).
A resting worker claims with no free slot, so it stays seen and gets its settings and orders,
and takes nothing, whatever coordinator it has; a withheld capability is left out of its claims.
A job that could not start keeps its result until the check that follows has run: when that check
fails, the result says `node_fault`, and a coordinator that knows it puts the job back in line.
"""

from __future__ import annotations

from typing import Any

from mulebox.common.log import get_logger
from mulebox.worker import background, health
from mulebox.worker.job import ActiveJob
from mulebox.worker.systemd import SystemdExecutor

LOG = get_logger("worker.health")


class Checking:
    def _health_state(self) -> dict[str, Any]:
        state = self.__dict__.get("_health")
        if state is None:
            state = self.__dict__["_health"] = {
                "task": None, "found": [], "since": {}, "next": 0.0, "asked": True,
                "streak": health.Streak(), "offered": [], "round": 0, "launched": 0,
                "pending_ask": False, "ask_launch": 0, "answers": 0}
        return state

    def _health_tick(self, now: float) -> None:
        """Take a finished check, start one when due; each step of the loop."""
        state = self._health_state()
        task = state["task"]
        if task is not None and task.done:
            state["task"] = None
            if task.error is not None:
                LOG.error("health check failed to run: %s", task.error)
            self._checked(state, now)
        if state["task"] is None and (state["asked"] or now >= state["next"]):
            state["asked"] = False
            state["launched"] += 1
            launched = state["launched"]
            if state["pending_ask"]:  # this check answers `mulebox machine check`
                state["pending_ask"], state["ask_launch"] = False, launched
            state["task"] = background.start_thread(lambda: self._run_checks(state, launched))

    def check_now(self, now: float) -> None:
        """The first check, before the claim loop (serve.py): a node that starts broken takes
        no job at all. At most a check's time limit for each check."""
        state = self._health_state()
        state["asked"] = False
        state["launched"] += 1
        self._run_checks(state, state["launched"])
        self._checked(state, now)

    def _run_checks(self, state: dict[str, Any], launched: int) -> None:
        offered = [*self.node.capabilities, *state["offered"]]  # the last claim's: Xcode found
        systemd = isinstance(self.executor, SystemdExecutor)
        state["found"] = health.run_all(self.node, self.paths, offered, self.docker,
                                        systemd=systemd)
        state["ran"] = health.ran(offered, systemd)
        state["checked"] = launched

    def _checked(self, state: dict[str, Any], now: float) -> None:
        found = state["found"]
        before = set(state["since"])
        names = {check for check, _, _ in found}
        state["since"] = {name: state["since"].get(name, now) for name in names}
        for check, message, fix in found:
            if check not in before:
                LOG.warning("health: %s; %s", message, fix)
        if "disk" in names - before:
            self._store()["urgent"] = True  # clean up first: the rest is the last resort
        for name in before - names - {"streak"}:
            LOG.info("health: %s passes again", name)
        state["next"] = now + (health.RETRY_S if found else health.EVERY_S)
        state["at"] = now
        state["round"] += 1
        if state["ask_launch"] and state.get("checked", 0) >= state["ask_launch"]:
            state["answers"], state["ask_launch"] = state["answers"] + 1, 0
        fault = "; ".join(message for _, message, _ in found)
        for job in self._judged(state.get("checked", 0)):
            job.judging = 0
            job.node_fault = (f"{self.node.name} could not set it up: {fault}"
                              if fault else None)

    def _judged(self, checked: int) -> list[ActiveJob]:
        """Jobs whose check ran: one started after the job failed."""
        return [job for job in self.finishing if job.judging and job.judging <= checked]

    def _health_report(self, now: float) -> dict[str, Any]:
        state = self._health_state()
        streak = state["streak"]
        since = dict(state["since"])
        if streak.until is not None:
            since["streak"] = streak.since or now
        seen = {"ran": state.get("ran", []), "checked_at": state.get("at"),
                "next_at": state["next"] or None, "min_free": self.node.storage.min_free_bytes()}
        return health.report(state["found"], since, state["offered"], streak, now, state["round"],
                             floor=self.node.isolation, answers=state["answers"], seen=seen)

    def _start_failed(self, job: ActiveJob, now: float) -> None:
        """A job that could not start: judge it by a check run now."""
        state = self._health_state()
        state["streak"].failed_start(job.project, now)
        job.judging = state["launched"] + 1  # the next check to start judges it
        state["asked"] = True

    def _command_started(self) -> None:
        self._health_state()["streak"].started()

    def _health_asked(self, body: dict[str, Any] | None) -> None:
        """`mulebox machine check` asked, through a claim's or heartbeat's reply."""
        if body and body.get("health_check"):
            state = self._health_state()
            state["asked"] = state["pending_ask"] = True

    def _claim_body(self, fields: dict[str, Any], free: int, now: float) -> dict[str, Any]:
        """The claim with this node's health: nothing taken while resting, a withheld
        capability left out, one job at a time on trial after a streak's rest."""
        offered = list(fields.get("capabilities") or [])
        self._health_state()["offered"] = offered
        report = self._health_report(now)
        state = self._health_state()
        if state["streak"].trial:
            free = min(free, max(0, 1 - len(self.active)))
        withheld = set(report["withheld"])
        return {**fields, "capabilities": [c for c in offered if c not in withheld],
                "free_slots": 0 if report["resting"] else free, "slots": self.node.slots,
                "health": report}

    def _heartbeat_health(self, now: float) -> dict[str, Any]:
        return {"health": self._health_report(now)}

    def _node_fault(self, job: ActiveJob) -> dict[str, Any]:
        return {"node_fault": job.node_fault} if job.node_fault else {}
