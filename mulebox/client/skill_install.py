"""The agent skill: the copy in this package and the copies in Claude config folders.

The skill ships inside the package, so a skill and the mulebox that wrote it have one version.
`SKILL.md` says which contract schema it was written for and `mulebox contract` prints the
current one, so an agent can tell that its copy is behind and tell the user. Agents never
update it: only a person runs `mulebox skill update`.

Several Claude config folders can exist on one machine: `~/.claude`, `~/.claude-work`, and
whatever `CLAUDE_CONFIG_DIR` names. A copy is in `<folder>/skills/mulebox/SKILL.md`. Only that
file is ever written, by rename, and a skill folder that is a link is left alone: writing
through it would change what it points to, such as a checkout.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

SKILL_NAME = "mulebox"
SKILL_FILE = "SKILL.md"
ENV_FOLDER = "CLAUDE_CONFIG_DIR"
HOME_FOLDERS = (".claude", ".claude-work")
_STAMP = re.compile(r"written for contract schema (\d+)")

MISSING = "not installed"
CURRENT = "current"
BEHIND = "behind"  # written for an older contract schema, or for none
DIFFERS = "differs"  # the same schema, other text: an older build's, or edited by hand
AHEAD = "ahead"  # written for a newer contract schema than this mulebox knows
LINKED = "linked"


@dataclass(frozen=True)
class Copy:
    folder: Path
    state: str
    schema: int | None = None

    @property
    def path(self) -> Path:
        return skill_path(self.folder)


def packaged_text() -> str:
    """SKILL.md as shipped in this package."""
    return (resources.files("mulebox.client") / "skill" / SKILL_FILE).read_text(encoding="utf-8")


def schema_of(text: str) -> int | None:
    """The contract schema a SKILL.md says it was written for."""
    found = _STAMP.search(text)
    return int(found[1]) if found else None


def skill_path(folder: Path) -> Path:
    return folder / "skills" / SKILL_NAME / SKILL_FILE


def config_folders(env: Mapping[str, str], home: Path) -> list[Path]:
    """The Claude config folders that exist here, each once, `CLAUDE_CONFIG_DIR` first."""
    named = env.get(ENV_FOLDER)
    candidates = ([Path(named).expanduser()] if named else [])
    candidates += [home / name for name in HOME_FOLDERS]
    found: dict[Path, Path] = {}
    for folder in candidates:
        if folder.is_dir():
            found.setdefault(folder.resolve(), folder)
    return list(found.values())


def inspect(folder: Path, packaged: str) -> Copy:
    """How the copy in `folder` stands against the packaged skill."""
    path = skill_path(folder)
    if path.parent.is_symlink() or path.is_symlink():
        return Copy(folder, LINKED)
    if not path.is_file():
        return Copy(folder, MISSING)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return Copy(folder, DIFFERS)
    schema, current = schema_of(text), schema_of(packaged)
    if text == packaged:
        return Copy(folder, CURRENT, schema)
    if schema is None or (current is not None and schema < current):
        return Copy(folder, BEHIND, schema)
    if current is not None and schema > current:
        return Copy(folder, AHEAD, schema)
    return Copy(folder, DIFFERS, schema)


def inspect_all(folders: Iterable[Path], packaged: str) -> list[Copy]:
    return [inspect(folder, packaged) for folder in folders]


def write(folder: Path, packaged: str) -> None:
    """Put the packaged skill into `folder`; whoever reads it sees the old text or the new."""
    path = skill_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{SKILL_FILE}.{os.getpid()}.tmp")
    try:
        temp.write_text(packaged, encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def install(copy: Copy, packaged: str) -> str:
    """Add the skill where it is missing; what `mulebox skill install` says about `copy`."""
    if copy.state == MISSING:
        write(copy.folder, packaged)
        return "installed"
    if copy.state in (CURRENT, LINKED):
        return f"already there ({copy.state})"
    return f"already there ({copy.state}); `mulebox skill update` replaces it"


def update(copy: Copy, packaged: str) -> str:
    """Replace an out-of-date copy; what `mulebox skill update` says about `copy`."""
    if copy.state in (BEHIND, DIFFERS):
        write(copy.folder, packaged)
        return "updated"
    if copy.state == AHEAD:
        return "left alone: it is newer than this mulebox; upgrade mulebox"
    if copy.state == LINKED:
        return "left alone: it is a link; update what it points to"
    if copy.state == MISSING:
        return "not installed here; `mulebox skill install` adds it"
    return "already current"
