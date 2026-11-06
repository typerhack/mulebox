"""What workers report with a claim, and the `machines` request that reads it back."""

from mulebox.common.config import NodeConfig
from mulebox.common.protocol import MessageType
from mulebox.coordinator import api
from mulebox.version import get_version
from mulebox.worker import advert, toolchains
from mulebox.worker.paths import NodePaths

from .helpers import request


def claim(store, staging, now=1000.0, **body):
    fields = {"worker": "build-1", "capabilities": ["docker"], "free_slots": 1, **body}
    return api.handle(store, staging, request("claim", **fields), now)


def machines(store, staging, now=1000.0):
    reply = api.handle(store, staging, request("machines"), now)
    assert reply.type is MessageType.MACHINES_OK, reply.body
    return reply.body


def test_a_claim_records_toolchains_and_version(store, staging):
    claim(store, staging, toolchains={"node": ["22.22.3"]}, version="1.2.3")
    body = machines(store, staging)
    assert body["version"] == get_version()
    assert body["workers"] == [{"worker": "build-1", "online": True, "capabilities": ["docker"],
                                "toolchains": {"node": ["22.22.3"]}, "version": "1.2.3",
                                "slots": 1, "disk_free": None}]


def test_an_older_worker_reports_nothing_and_keeps_what_it_said(store, staging):
    claim(store, staging)
    assert machines(store, staging)["workers"][0]["toolchains"] is None
    claim(store, staging, toolchains={"pnpm": ["11.22.0"]}, version="1.2.3")
    claim(store, staging)
    worker = machines(store, staging)["workers"][0]
    assert worker["toolchains"] == {"pnpm": ["11.22.0"]} and worker["version"] == "1.2.3"


def test_online_follows_last_seen(store, staging):
    claim(store, staging, now=1000.0)
    assert machines(store, staging, now=1100.0)["workers"][0]["online"] is False


def test_bad_toolchains_are_refused(store, staging):
    reply = claim(store, staging, toolchains={"node": "22.22.3"})
    assert reply.type is MessageType.ERROR and reply.body["code"] == "bad_request"


def test_machines_is_read_only(store, staging):
    machines(store, staging)
    assert machines(store, staging)["workers"] == []


def test_advert_groups_versions_by_name(tmp_path, root_map):
    paths = NodePaths.from_config(root_map)
    for name, version in (("node", "22.9.0"), ("node", "20.18.1"), ("pnpm", "11.22.0")):
        (toolchains.toolchain_dir(paths, name, version) / "bin").mkdir(parents=True)
    node = NodeConfig(name="build-1", roles=("worker",), roots=root_map, capabilities=("docker",))
    fields = advert.fields(node, paths)
    assert fields["toolchains"] == {"node": ["20.18.1", "22.9.0"], "pnpm": ["11.22.0"]}
    assert fields["worker"] == "build-1" and fields["version"] == get_version()
    assert "docker" in fields["capabilities"]


def test_a_low_disk_reaches_a_project_s_next_command(store, staging):
    from mulebox.coordinator import queue, workers

    queue.claim(store, "build-1", [], 1, now=100.0, disk_free=2_000_000_000)
    queue.claim(store, "build-2", [], 1, now=100.0, disk_free=90_000_000_000)
    with store.read() as conn:
        assert workers.low_disks(conn, 101.0) == [{"worker": "build-1", "free": 2_000_000_000}]
        assert workers.low_disks(conn, 1000.0) == []  # offline: no job goes there
