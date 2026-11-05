"""The compose problems `mulebox doctor` can see before anything is uploaded.

The worker's policy (worker/compose_policy.py) decides; this only gives it a model it can read
on a client, which may have no Docker. The worker gets that model from `docker compose config`,
so this does by hand the few things that command does to the files: merge them (compose_yaml),
leave out what an inactive profile hides, drop what no service uses, spell short volumes out,
and resolve relative paths against the first file's folder.

What is not in the files is left out, not guessed: values with a variable in them, and whatever
`include` and `extends` pull in. So a problem found here is one the worker would refuse too,
and a clean result promises nothing: the worker still makes the final check.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import Any

from mulebox.client import compose_yaml
from mulebox.client.doctor import FAIL, OK, WARN, Finding
from mulebox.common.compose import ComposeError
from mulebox.common.config_reader import ConfigError
from mulebox.worker import compose_policy

Model = dict[str, Any]

TOPIC = "compose"
_VARIABLE = re.compile(r"(?<!\$)\$(?!\$)")  # `$$` is a literal dollar sign
_PATH_START = (".", "/", "~")
_SHARED = ("volumes", "networks", "secrets", "configs")


def _known(value: Any) -> Any:
    """`value` without what only the machine can fill in."""
    if isinstance(value, dict):
        return {key: _known(item) for key, item in value.items() if not _unresolved(item)}
    if isinstance(value, list):
        return [_known(item) for item in value if not _unresolved(item)]
    return value


def _unresolved(value: Any) -> bool:
    return isinstance(value, str) and _VARIABLE.search(value) is not None


def _resolved(source: str, base: str) -> str:
    if source.startswith(("/", "~")):
        return source
    return posixpath.normpath(posixpath.join(base, source))


def _short_volume(text: str, base: str) -> Model:
    """`source:target[:mode]` or a bare target, as `docker compose config` spells it out."""
    source, _, rest = text.partition(":")
    if not rest:
        return {"type": "volume", "target": source}
    target, _, mode = rest.partition(":")
    if not source.startswith(_PATH_START):
        return {"type": "volume", "source": source, "target": target}
    modes = mode.split(",")
    volume = {"type": "bind", "source": _resolved(source, base), "target": target,
              "read_only": "ro" in modes}
    selinux = next((item for item in modes if item in ("z", "Z")), None)
    return {**volume, "bind": {"selinux": selinux}} if selinux else volume


def _volume(volume: Any, base: str) -> Model:
    if isinstance(volume, str):
        return _short_volume(volume, base)
    if volume.get("type") == "bind" and volume.get("source"):
        return {**volume, "source": _resolved(volume["source"], base)}
    return volume


def _with_volumes(spec: Model, base: str) -> Model:
    """One entry per target, the later one, as a later file replaces a mount."""
    volumes = [_volume(item, base) for item in spec.get("volumes") or []]
    return {**spec, "volumes": list({item.get("target"): item for item in volumes}.values())}


def _named(entries: Any) -> set[str]:
    """Names in a service's `networks`, `secrets` or `configs`, in either spelling."""
    if isinstance(entries, dict):
        return set(entries)
    return {item if isinstance(item, str) else item.get("source") for item in entries or []}


def _used(section: str, active: Model) -> set[str]:
    used: set[str] = set()
    for spec in active.values():
        if section == "volumes":
            used |= {item.get("source") for item in spec["volumes"]
                     if item.get("type") == "volume"}
        elif section != "networks":
            used |= _named(spec.get(section))
        elif not spec.get("network_mode"):
            used |= _named(spec.get("networks")) or {"default"}
    return used


def model_of(raw: Model, first_file: str) -> Model:
    """`raw`, the merged files, in the shape `docker compose config` would print."""
    known, base = _known(raw), posixpath.dirname(first_file)
    services = {name: _with_volumes(spec, base)
                for name, spec in (known.get("services") or {}).items()}
    active = {name: spec for name, spec in services.items() if not spec.get("profiles")}
    model: Model = {"services": {name: active.get(name, {}) for name in services}}
    for section in _SHARED:  # a service left out keeps its name, for those that refer to it
        used = _used(section, active)
        model[section] = {key: spec for key, spec in (known.get(section) or {}).items()
                          if key in used}
    return model


def _followed(raw: Model) -> str:
    services = raw.get("services") or {}
    skipped = bool(raw.get("include")) or any(
        isinstance(spec, dict) and spec.get("extends") for spec in services.values())
    return " Files named by include or extends were not read." if skipped else ""


def findings(files: tuple[str, ...], root: Path) -> list[Finding]:
    """What can be said about these compose files, without Docker and without the machine."""
    if not files:
        return []
    try:
        raw = compose_yaml.load(root, files)
        compose_policy.check(model_of(raw, files[0]), None)
    except ConfigError as exc:
        return [Finding(WARN, TOPIC, f"could not check the compose files: {exc}")]
    except ComposeError as exc:
        return [Finding(FAIL, TOPIC, f"a worker would refuse this project: {exc}")]
    except (AttributeError, TypeError):  # Compose reports a file of a wrong shape better
        return [Finding(WARN, TOPIC, "could not check the compose files: an unexpected shape")]
    return [Finding(OK, TOPIC, f"nothing in {', '.join(files)} that a worker would refuse; it "
                    f"still checks the final model.{_followed(raw)}")]
