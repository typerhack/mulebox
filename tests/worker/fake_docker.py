"""A fake Docker daemon behind the runner seam. No test ever talks to a real Docker.

It holds resources with labels, answers the same CLI calls the worker makes, applies filters
the way the daemon does (every filter must match), and records every call, so a test can
prove what would have been removed, and that what belongs to others was left alone.
"""

import subprocess
from dataclasses import dataclass, field

LIST_COMMANDS = {("ps",): "containers", ("network", "ls"): "networks",
                 ("volume", "ls"): "volumes", ("image", "ls"): "images"}
REMOVE_COMMANDS = {("rm",): "containers", ("network", "rm"): "networks",
                   ("volume", "rm"): "volumes", ("image", "rm"): "images"}


@dataclass
class Resource:
    kind: str
    rid: str
    labels: dict[str, str] = field(default_factory=dict)


class FakeDocker:
    def __init__(self):
        self.resources: list[Resource] = []
        self.calls: list[tuple[str, ...]] = []
        self.envs: list[dict | None] = []
        self.responses: dict[tuple[str, ...], subprocess.CompletedProcess] = {}
        self.fail_remove: dict[str, int] = {}  # kind -> how many removals fail
        self.missing = False

    def add(self, kind, rid, **labels):
        self.resources.append(Resource(kind, rid, {k.replace("__", "."): v
                                                   for k, v in labels.items()}))

    def add_labelled(self, kind, rid, labels):
        self.resources.append(Resource(kind, rid, labels))

    def left(self, kind=None):
        return [r.rid for r in self.resources if kind is None or r.kind == kind]

    def removals(self):
        return [c for c in self.calls if any(c[:len(k)] == k for k in REMOVE_COMMANDS)]

    def __call__(self, argv, env, cwd, timeout_s):
        from mulebox.worker.docker import DockerMissing

        assert argv[0] == "docker"
        if self.missing:
            raise DockerMissing("the docker command is not installed on this machine")
        args = tuple(argv[1:])
        self.calls.append(args)
        self.envs.append(dict(env) if env is not None else None)
        for prefix, reply in self.responses.items():
            if args[:len(prefix)] == prefix:
                return reply
        for words, kind in LIST_COMMANDS.items():
            if args[:len(words)] == words:
                return self._list(kind, args)
        for words, kind in REMOVE_COMMANDS.items():
            if args[:len(words)] == words:
                return self._remove(kind, args[len(words):])
        return ok()

    def _list(self, kind, args):
        filters = [args[i + 1] for i, word in enumerate(args) if word == "--filter"]
        matches = [r for r in self.resources if r.kind == kind and _matches(r, filters)]
        if kind == "images":  # listed by repository:tag, one line per tag
            lines = [r.rid for r in matches]
        elif "--format" in args:
            lines = [r.labels.get("mulebox.job", "") for r in matches]
        else:
            lines = [r.rid for r in matches]
        return ok("".join(f"{line}\n" for line in lines))

    def _remove(self, kind, args):
        if self.fail_remove.get(kind, 0) > 0:
            self.fail_remove[kind] -= 1
            return subprocess.CompletedProcess([], 1, "", f"{kind} are in use")
        ids = [a for a in args if not a.startswith("--")]
        self.resources = [r for r in self.resources if not (r.kind == kind and r.rid in ids)]
        return ok()


def _matches(resource, filters):
    for item in filters:
        assert item.startswith("label="), f"unexpected filter {item}"
        key, sep, value = item[len("label="):].partition("=")
        if key not in resource.labels or (sep and resource.labels[key] != value):
            return False
    return True


def ok(stdout=""):
    return subprocess.CompletedProcess([], 0, stdout, "")
