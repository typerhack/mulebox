"""Work out a project's `.mulebox.yml` from the files it already has.

Reads manifests, and asks this computer's node and pnpm for their versions; runs nothing of
the project's. Each language gives its install step and its checks; a project with several
gets them all, and one with no checks at its root is looked for one folder down, so
`api/` and `web/` both count. What the project's CI uses comes first: its compose files and its
Node version (init_ci.py). A folder a compose service is built from has its tools run in that
image (`docker compose exec`), as `install` and in the checks. A guess the user must look at goes
in `notes`, and only an exact version is ever pinned as a toolchain.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from mulebox.client import gitinfo, init_ci
from mulebox.client.init_files import IN_SERVICE, Detected, json_file, mapping, text
from mulebox.client.init_langs import PYTHON_FILES, composer, flutter, python
from mulebox.common import package_cache

LOCKFILES = (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("package-lock.json", "npm"))
INSTALL = {"pnpm": "pnpm install --frozen-lockfile", "npm": "npm ci",
           "yarn": "yarn install --frozen-lockfile"}
CACHE = {"pnpm": package_cache.PNPM, "npm": package_cache.NPM}
SCRIPTS = (("lint", "lint"), ("typecheck", "typecheck"), ("type-check", "typecheck"),
           ("test", "test"))
COMPOSE_FILES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
NO_TEST_SCRIPT = "no test specified"
NOT_PROJECTS = frozenset({"node_modules", "vendor", "dist", "build", "target", "docs"})
VERSION_TIMEOUT_S = 5
_EXACT = re.compile(r"v?(\d+\.\d+\.\d+)")
_MAJOR = re.compile(r"\D*(\d+)")
_OVERLAY = re.compile(r"(docker-)?compose\.(ci|test)[.-]?[\w-]*\.ya?ml")
_PACKAGE_MANAGER = re.compile(r"(pnpm|npm|yarn)@(\d+\.\d+\.\d+)")
_NOT_A_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def project_name(root: Path) -> str:
    """The folder's name, and in a git worktree the repository's: a project's caches and folder
    on a machine go by this name, so its worktrees must share it."""
    folder = gitinfo.main_checkout(root) or root.resolve()
    return _NOT_A_NAME.sub("-", folder.name).strip("-._") or "project"


def _node_version(root: Path, package: dict[str, Any], top: Path) -> str | None:
    """The first place that says, exact or not, the project's CI last. Only an exact version can
    be pinned."""
    for name in (".nvmrc", ".node-version"):
        said = text(root / name).strip()
        if said:
            return said
    tools = re.search(r"^nodejs?\s+(\S+)", text(root / ".tool-versions"), re.MULTILINE)
    if tools:
        return tools.group(1)
    said = mapping(package, "volta").get("node") or mapping(package, "engines").get("node")
    return said if isinstance(said, str) else init_ci.ci_node_version(top)


def local_version(tool: str) -> str | None:
    """The exact version of `tool` on this computer, or None."""
    path = shutil.which(tool)
    if path is None:
        return None
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True,
                             timeout=VERSION_TIMEOUT_S, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    match = _EXACT.fullmatch(out)
    return match.group(1) if match else None


def _pin(found: Detected, tool: str, said: str | None) -> None:
    """Pin `said` if exact, else what this computer has, as that is what works here today."""
    exact = _EXACT.fullmatch(said) if said else None
    if exact:
        found.toolchain[tool] = exact.group(1)
        return
    local = local_version(tool)
    project_says = f"the project says {said!r}" if said else "the project does not say"
    major = int(m.group(1)) if said and (m := _MAJOR.match(said)) else None
    if local and (major is None or local.split(".")[0] == str(major)):
        found.toolchain[tool] = local
        found.notes.append(f"{tool}: pinned {local}, the version on this computer; "
                           f"{project_says}")
        return
    newest = init_ci.newest_node(major) if tool == "node" and major is not None else None
    if newest:
        found.toolchain[tool] = newest
        found.notes.append(f"{tool}: pinned {newest}, the newest {major}.x; {project_says}")
    elif major is not None:
        found.notes.append(f"{tool}: {project_says}; pin an exact {major}.x version in "
                           f"`toolchain:`, as nothing is pinned and the machine's own is used")
    else:
        found.notes.append(f"{tool}: {project_says}, and this computer has none, so nothing "
                           f"is pinned and the machine's own is used")


def _node_manager(root: Path, package: dict[str, Any]) -> tuple[str, str | None]:
    """(package manager, its exact version if the project pins one)."""
    declared = package.get("packageManager")
    match = _PACKAGE_MANAGER.match(declared) if isinstance(declared, str) else None
    if match:
        return match.group(1), match.group(2)
    return next((tool for lock, tool in LOCKFILES if (root / lock).is_file()), "npm"), None


def _node(root: Path, found: Detected, top: Path) -> None:
    package = json_file(root / "package.json")
    manager, version = _node_manager(root, package)
    _pin(found, "node", _node_version(root, package, top))
    if manager == "pnpm":
        _pin(found, "pnpm", version)
    elif manager == "yarn":
        found.notes.append("yarn: mulebox has no yarn toolchain, so the machine must have it")
    if not any((root / lock).is_file() for lock, _ in LOCKFILES):
        found.notes.append("no lockfile found: the install step needs one to be repeatable")
    found.setup.append(INSTALL[manager])
    if manager in CACHE:
        found.needs.append(CACHE[manager])
    scripts = mapping(package, "scripts")
    usable = {name: value for name, value in scripts.items()
              if isinstance(value, str) and NO_TEST_SCRIPT not in value}
    for script, job in SCRIPTS:
        if script in usable:
            found.jobs.setdefault(job, f"{manager} run {script}")
    if "build" in usable:
        found.jobs.setdefault("build", f"{manager} run build")
    if "check" in usable:
        found.checks.append(f"{manager} run check")
        return
    found.checks.extend(f"{manager} run {script}" for script, _ in SCRIPTS if script in usable)
    if "build" in usable and "test" not in usable:  # the heavy step should not stay behind
        found.checks.append(f"{manager} run build")


def _make_target(root: Path) -> str | None:
    makefile = text(root / "Makefile")
    return next((name for name in ("check", "test")
                 if re.search(rf"^{name}\s*:", makefile, re.MULTILINE)), None)


def _languages(root: Path, found: Detected, top: Path) -> None:
    if (root / "composer.json").is_file():
        composer(root, found)
    if any((root / name).is_file() for name in PYTHON_FILES):
        python(root, found)
    if (root / "package.json").is_file():
        _node(root, found, top)
    if (root / "pubspec.yaml").is_file():
        flutter(root, found)
    for manifest, command, tool in (("go.mod", "go test ./...", "go"),
                                    ("Cargo.toml", "cargo test", "cargo")):
        if (root / manifest).is_file():
            found.jobs.setdefault("test", command)
            found.checks.append(command)
            found.notes.append(f"{tool}: the machine must have it installed")


def _add_folder(found: Detected, folder: Path) -> None:
    """A part of the project in its own folder: the same, run from that folder."""
    part = Detected(found.project, services=found.services)
    _languages(folder, part, top=folder.parent)
    name = folder.name
    def there(command: str, group: bool = True) -> str:
        if command.startswith(IN_SERVICE):  # already where the service keeps that folder
            return command
        return f"({within}{command})" if group else f"{within}{command}"
    within = f"cd {shlex.quote(name)} && "
    found.install.extend(part.install)
    found.setup.extend(there(command) for command in part.setup)
    found.checks.extend(there(command) for command in part.checks)
    found.jobs.update({f"{name}-{job}": there(command, group=False)
                       for job, command in part.jobs.items()})
    found.needs.extend(part.needs)
    found.notes.extend(f"{name}/ {note}" for note in part.notes
                       if note not in found.notes)
    for tool, version in part.toolchain.items():
        found.toolchain.setdefault(tool, version)


def _compose_files(root: Path, found: Detected) -> list[str]:
    """CI's list, else the main file and its CI or test overlays."""
    files = init_ci.ci_compose_files(root)
    if files:
        found.notes.append(f"compose: {', '.join(files)}, as the project's CI uses them")
        return files
    base = [name for name in COMPOSE_FILES if (root / name).is_file()][:1]
    if not base:
        return []
    overlays = sorted(p.name for p in root.iterdir() if p.is_file() and _OVERLAY.fullmatch(p.name))
    found.notes.append(f"{base[0]}: its containers start before every job, and commands run on "
                       "the machine; to run one inside a container, use "
                       "`docker compose exec -T <service> ...`")
    if overlays:
        found.notes.append(f"compose: {', '.join(overlays)} added over {base[0]}, by name")
    return base + overlays


def detect(root: Path) -> Detected:
    """What `root` looks like. `checks` is empty when no way to test it could be found."""
    found = Detected(project_name(root))
    found.compose = _compose_files(root, found)
    found.services = init_ci.services_by_folder(root, found.compose)
    _languages(root, found, root)
    if not found.checks:
        for folder in sorted(path for path in root.iterdir() if path.is_dir()):
            if not folder.name.startswith(".") and folder.name not in NOT_PROJECTS:
                _add_folder(found, folder)
    if not found.checks and (target := _make_target(root)):
        found.checks.append(f"make {target}")
    return found
