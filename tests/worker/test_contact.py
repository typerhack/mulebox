"""The worker's word that it reached its coordinator, for an upgrade's trial (worker/contact.py)."""

import os

from mulebox.common.protocol import MessageType
from mulebox.version import get_version
from mulebox.worker import contact

from .test_agent import agent, clock, executor  # noqa: F401


def test_the_first_reply_is_recorded_once_with_version_and_pid(agent, fake_link, paths):
    assert contact.read(paths) is None
    fake_link.down = True
    agent.step()
    assert contact.read(paths) is None  # unreachable: nothing to say
    fake_link.down = False
    agent.retry_at = 0
    agent.step()
    said = contact.read(paths)
    assert said["version"] == get_version() and said["pid"] == os.getpid()
    contact.path(paths).unlink()
    agent.retry_at = 0
    agent.step()
    assert contact.read(paths) is None  # once per process


def test_a_refusal_is_no_contact(agent, fake_link, paths):
    fake_link.refuse.add(MessageType.CLAIM)
    agent.step()
    assert contact.read(paths) is None
