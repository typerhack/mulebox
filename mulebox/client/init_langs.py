"""`mulebox init` for PHP (Composer), Python and Flutter projects (init_detect.py has Node and
the rest). A PHP folder a compose service is built from runs composer and its tests there."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

from mulebox.client.init_files import IN_SERVICE, Detected, json_file, mapping, text
from mulebox.common import package_cache

VENV = ".venv"
PYTHON_FILES = ("pyproject.toml", "requirements.txt", "requirements-dev.txt")


def _python_install(root: Path) -> str | None:
    if (root / "pyproject.toml").is_file():
        try:
            data = tomllib.loads(text(root / "pyproject.toml"))
        except tomllib.TOMLDecodeError:
            data = {}
        extras = mapping(mapping(data, "project"), "optional-dependencies")
        if mapping(data, "project"):
            return "-e '.[dev]'" if "dev" in extras else "-e ."
    for name in ("requirements-dev.txt", "requirements.txt"):
        if (root / name).is_file():
            return f"-r {name}"
    return None


def python(root: Path, found: Detected) -> None:
    install = _python_install(root)
    if install is None:
        found.notes.append("python: no [project] table or requirements file, so nothing is "
                           "installed; add the install step to setup")
        return
    found.setup.append(f"python3 -m venv {VENV} && "
                       f"{VENV}/bin/pip install -q --disable-pip-version-check {install}")
    found.venv = VENV
    found.needs.append(package_cache.PIP)
    found.notes.append("python: the machine's python3 is used, as mulebox has no Python "
                       "toolchain")
    if _uses_pytest(root):
        found.jobs.setdefault("test", f"{VENV}/bin/python -m pytest")
        found.checks.append(f"{VENV}/bin/python -m pytest")
    if not _ignored(root, VENV):
        found.notes.append(f"python: add `{VENV}/` to .gitignore; setup makes it, and a folder "
                           "git does not ignore is lost between jobs, so setup runs every time")


def _uses_pytest(root: Path) -> bool:
    if (root / "tests").is_dir() or (root / "test").is_dir():
        return True
    if any(root.glob("test_*.py")) or any(root.glob("*_test.py")):
        return True
    return any(re.search(r"(?m)\bpytest\b", text(root / name)) for name in PYTHON_FILES
               if (root / name).is_file())


def _ignored(root: Path, folder: str) -> bool:
    """Whether git ignores `folder`; True when git cannot say, so no false warning."""
    try:
        done = subprocess.run(["git", "check-ignore", "-q", f"{folder}/"], cwd=root,
                              capture_output=True, check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return True
    return done.returncode != 1


_IN_VENV = {"python": "python", "python3": "python", "pytest": "pytest", "pip": "pip",
            "pip3": "pip"}


def in_venv(command: str, venv: str | None) -> str:
    """A command given with `--check`, its first word called from setup's venv: a venv that
    is made but never activated is not on PATH, and Ubuntu has no `python` at all."""
    first, _, rest = command.strip().partition(" ")
    if venv is None or first not in _IN_VENV:
        return command
    return f"{venv}/bin/{_IN_VENV[first]}" + (f" {rest}" if rest else "")


def composer(root: Path, found: Detected) -> None:
    composer = json_file(root / "composer.json")
    service = found.services.get(root.resolve())
    within = f"{IN_SERVICE} -T {service} " if service else ""
    install = f"{within}composer install --no-interaction --prefer-dist"
    (found.install if service else found.setup).append(install)
    found.needs.append(package_cache.COMPOSER)
    dev = mapping(composer, "require-dev")
    if "test" in mapping(composer, "scripts"):
        command = "composer test"
    elif (root / "artisan").is_file():
        command = "php artisan test"
    elif "pestphp/pest" in dev:
        command = "vendor/bin/pest"
    elif "phpunit/phpunit" in dev:
        command = "vendor/bin/phpunit"
    else:
        command = None
    if command:
        found.jobs.setdefault("test", within + command)
        found.checks.append(within + command)
    if service:
        found.notes.append(f"php: composer and the tests run in the `{service}` service, built "
                           f"from {root.name}/")
    else:
        found.notes.append("php: the machine must have php and composer, or run them in a "
                           "container with `docker compose exec -T <service> ...`")
    if (root / "artisan").is_file():
        found.notes.append("laravel: with no .env (mulebox never uploads one) Laravel takes "
                           "APP_ENV=production; give the job its environment in `env:`")


def flutter(root: Path, found: Detected) -> None:
    found.setup.append("flutter pub get")
    found.jobs.setdefault("analyze", "flutter analyze")
    found.checks.append("flutter analyze")
    if (root / "test").is_dir():
        found.jobs.setdefault("test", "flutter test")
        found.checks.append("flutter test")
    found.notes.append("flutter: the machine must have it installed")
