"""The worker takes a change of its settings with no restart (worker/live_config.py, M23.9)."""

import time

from mulebox.common.config import load_node_config
from mulebox.common.protocol import Message, MessageType
from mulebox.worker.agent import Agent
from mulebox.worker.executor import SubprocessExecutor
from mulebox.worker.live_config import LiveConfig
from mulebox.worker.link import LocalLink

from .fakes import FakeLink, claim_body


class SettingsLink(FakeLink):
    """A coordinator holding a change for this node until a claim reports it."""

    def __init__(self, snapshot, wanted):
        super().__init__(snapshot)
        self.wanted = wanted

    def call(self, msg):
        reply = super().call(msg)
        settings = msg.body.get("settings") or {}
        if msg.type in (MessageType.CLAIM, MessageType.HEARTBEAT) and self.wanted:
            if all(settings.get(key) == value for key, value in self.wanted.items()):
                self.wanted = None
            else:
                reply = Message(reply.type, reply.request_id,
                                {**reply.body, "node_settings": self.wanted, "node_settings_at": 1.0})
        return reply


def node_toml(tmp_path, roots, slots):
    folder = tmp_path / "config"
    folder.mkdir()
    path = folder / "node.toml"
    lines = ['name = "build-1"', 'roles = ["coordinator", "worker"]', f"slots = {slots}",
             'capabilities = ["node"]', "[roots]", *(f'{k} = "{v}"' for k, v in roots.items())]
    path.write_text("\n".join(lines) + "\n")
    return path


def test_more_slots_from_afar_count_from_the_next_claim(tmp_path, roots_config, paths, snapshot):
    path = node_toml(tmp_path, roots_config, 1)
    link = SettingsLink(snapshot, {"slots": 3})
    agent = Agent(load_node_config(path), link, SubprocessExecutor(grace_s=0.5), paths,
                  live=LiveConfig(path))
    agent.step()
    assert agent.node.slots == 3 and "slots = 3" in path.read_text()
    agent.step()
    claims = link.of_type(MessageType.CLAIM)
    assert claims[-1].body["settings"] == {"slots": 3, "priority": "normal", "dev": False}
    assert claims[-1].body["free_slots"] == 3 and link.wanted is None


def test_fewer_slots_than_running_jobs_stops_no_job(tmp_path, roots_config, paths, snapshot):
    path = node_toml(tmp_path, roots_config, 2)
    link = SettingsLink(snapshot, None)
    agent = Agent(load_node_config(path), link, SubprocessExecutor(grace_s=0.5), paths,
                  live=LiveConfig(path))
    for _ in range(2):
        link.claims.append(claim_body(["sleep", "2"]))
    end = time.monotonic() + 10
    while len(agent.active) < 2 and time.monotonic() < end:
        agent.step()
        time.sleep(0.05)
    assert len(agent.active) == 2
    link.wanted = {"slots": 1}
    agent.last_reply = agent.clock()
    for job in agent.active.values():
        job.last_heartbeat = 0.0  # a heartbeat goes out on this step
    agent.step()
    assert agent.node.slots == 1 and len(agent.active) == 2  # both keep running
    assert agent._free_slots() < 1
    sent = len(link.of_type(MessageType.CLAIM))
    agent.step()
    assert len(link.of_type(MessageType.CLAIM)) == sent  # no claim while over the new count
    agent.shutdown()


def test_the_local_coordinators_least_follows_the_slots(tmp_path, roots_config, paths):
    path = node_toml(tmp_path, roots_config, 1)
    link = LocalLink(store=None, staging=None, cluster_slots=1)
    agent = Agent(load_node_config(path), link, SubprocessExecutor(), paths, live=LiveConfig(path))
    agent._settings({"node_settings": {"slots": 4}, "node_settings_at": 1.0})
    assert link.cluster_slots == 4
