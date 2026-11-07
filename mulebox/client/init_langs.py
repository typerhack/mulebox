"""`mulebox init` for PHP (Composer), Python and Flutter projects (init_detect.py has Node and
the rest). A PHP folder a compose service is built from runs composer and its tests there."""

from __future__ import annotations

import tomllib
from pathlib import Path

from mulebox.client.init_files import IN_SERVICE, Detected, json_file, mapping, text
from mulebox.common import package_cache


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
    found.setup.append("python3 -m venv .venv && "
                       f".venv/bin/pip install -q --disable-pip-version-check {install}")
    found.needs.append(package_cache.PIP)
    found.notes.append("python: the machine's python3 is used, as mulebox has no Python "
                       "toolchain")
    if (root / "tests").is_dir() or (root / "test").is_dir():
        found.jobs.setdefault("test", ".venv/bin/python -m pytest")
        found.checks.append(".venv/bin/python -m pytest")


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
