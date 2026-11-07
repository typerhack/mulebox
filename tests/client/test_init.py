"""`mulebox init`: real project layouts in, a valid `.mulebox.yml` out."""

import json
import subprocess

import pytest

from mulebox import cli
from mulebox.client import init_ci, init_detect
from mulebox.common.config import PROJECT_FILE, load_project_config


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "Example App"
    root.mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setattr(init_detect, "local_version", lambda tool: None)
    monkeypatch.setattr(init_ci, "newest_node", lambda major: None)  # no network in tests
    return root


def _package(root, **fields):
    (root / "package.json").write_text(json.dumps(fields))


def _init(root, *args):
    code = cli.main(["init", *args])
    assert code == 0
    return load_project_config(root / PROJECT_FILE)


def test_pnpm_project(project):
    _package(project, packageManager="pnpm@11.22.0+sha512.abc",
             scripts={"lint": "eslint .", "typecheck": "tsc", "test": "vitest", "build": "vite"})
    (project / "pnpm-lock.yaml").write_text("")
    (project / ".nvmrc").write_text("v22.22.3\n")
    config = _init(project)
    assert config.project == "Example-App"
    assert config.toolchain == {"node": "22.22.3", "pnpm": "11.22.0"}
    assert config.setup == "pnpm install --frozen-lockfile"
    assert config.needs == ("cache-pnpm",)
    assert config.jobs["check"] == "pnpm run lint && pnpm run typecheck && pnpm run test"
    assert config.jobs["build"] == "pnpm run build"


def test_a_check_script_is_the_gate(project):
    _package(project, scripts={"check": "all", "test": "vitest"})
    (project / "package-lock.json").write_text("{}")
    config = _init(project)
    assert config.jobs["check"] == "npm run check"
    assert config.jobs["test"] == "npm run test"
    assert config.setup == "npm ci"
    assert config.needs == ("cache-npm",)


@pytest.mark.parametrize("said", ["22", "lts/*", ">=20", "$(rm -rf /)"])
def test_only_an_exact_version_is_pinned(project, capsys, said):
    _package(project, engines={"node": said}, scripts={"test": "x"})
    assert _init(project).toolchain == {}
    assert "nothing is pinned" in capsys.readouterr().out


def test_this_computers_version_is_pinned_when_the_project_gives_none(project, capsys,
                                                                      monkeypatch):
    monkeypatch.setattr(init_detect, "local_version", {"node": "22.22.3", "pnpm": "11.25.0"}.get)
    _package(project, engines={"node": ">=22"}, scripts={"test": "x"})
    (project / "pnpm-lock.yaml").write_text("")
    assert _init(project).toolchain == {"node": "22.22.3", "pnpm": "11.25.0"}
    assert "pinned 22.22.3, the version on this computer" in capsys.readouterr().out


def test_real_local_version_reads_an_exact_version_only(tmp_path, monkeypatch):
    monkeypatch.undo()
    tool = tmp_path / "tool"
    tool.write_text("#!/bin/sh\necho v1.2.3\n")
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert init_detect.local_version("tool") == "1.2.3"
    assert init_detect.local_version("absent") is None
    tool.write_text("#!/bin/sh\necho nonsense\n")
    assert init_detect.local_version("tool") is None


def test_a_build_is_the_gate_when_there_are_no_tests(project):
    _package(project, scripts={"lint": "eslint", "build": "next build"})
    assert _init(project).jobs["check"] == "npm run lint && npm run build"


def test_a_build_alone_is_enough_for_a_gate(project):
    _package(project, scripts={"build": "esbuild"})
    assert _init(project).jobs["check"] == "npm run build"


def test_parts_in_their_own_folders(project):
    (project / "api").mkdir()
    (project / "web").mkdir()
    (project / "docs").mkdir()
    (project / "docs" / "package.json").write_text('{"scripts": {"test": "no"}}')
    (project / "api" / "composer.json").write_text('{"scripts": {"test": "phpunit"}}')
    _package(project / "web", scripts={"test": "vitest"})
    (project / "web" / "pnpm-lock.yaml").write_text("")
    config = _init(project)
    assert config.jobs["check"] == "(cd api && composer test) && (cd web && pnpm run test)"
    assert "(cd web && pnpm install --frozen-lockfile)" in config.setup
    assert config.jobs["web-test"] == "cd web && pnpm run test"
    assert set(config.needs) == {"cache-composer", "cache-pnpm"}


def test_flutter(project):
    (project / "pubspec.yaml").write_text("name: x\n")
    (project / "test").mkdir()
    config = _init(project)
    assert config.setup == "flutter pub get"
    assert config.jobs["check"] == "flutter analyze && flutter test"


def test_npm_default_test_script_is_no_test(project):
    _package(project, scripts={"test": 'echo "Error: no test specified" && exit 1'})
    assert cli.main(["init"]) == 2
    assert not (project / PROJECT_FILE).exists()


def test_python_project(project):
    (project / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1"\n[project.optional-dependencies]\ndev = ["pytest"]\n')
    (project / "tests").mkdir()
    config = _init(project)
    assert ".venv/bin/pip install" in config.setup and "-e '.[dev]'" in config.setup
    assert config.jobs["check"] == ".venv/bin/python -m pytest"
    assert config.needs == ("cache-pip",)


def test_php_and_node_together(project):
    (project / "composer.json").write_text(json.dumps({"require-dev": {"phpunit/phpunit": "^11"}}))
    _package(project, scripts={"test": "vitest"})
    (project / "pnpm-lock.yaml").write_text("")
    config = _init(project)
    assert config.jobs["check"] == "vendor/bin/phpunit && pnpm run test"
    assert set(config.needs) == {"cache-composer", "cache-pnpm"}


@pytest.mark.parametrize(("name", "gate"), [("go.mod", "go test ./..."),
                                            ("Cargo.toml", "cargo test")])
def test_go_and_rust(project, name, gate):
    (project / name).write_text("")
    assert _init(project).jobs["check"] == gate


def test_makefile_is_the_fallback(project):
    (project / "Makefile").write_text("build:\n\ttrue\ntest:\n\ttrue\n")
    assert _init(project).jobs["check"] == "make test"


def test_compose_file_is_listed(project):
    (project / "go.mod").write_text("")
    (project / "docker-compose.yml").write_text("services: {}\n")
    assert _init(project).compose == ("docker-compose.yml",)


def test_plain_python_project_with_root_tests(project, capsys):
    """The agent trial's project: requirements.txt and test_*.py, no tests/ folder."""
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / "requirements.txt").write_text("pytest==8.3.3\n")
    (project / "test_calc.py").write_text("def test_add():\n    assert 1 + 1 == 2\n")
    config = _init(project)
    assert config.jobs["check"] == ".venv/bin/python -m pytest"
    assert "add `.venv/` to .gitignore" in capsys.readouterr().out


def test_pytest_named_in_requirements_is_found(project):
    (project / "requirements-dev.txt").write_text("pytest>=8\n")
    assert _init(project).jobs["check"] == ".venv/bin/python -m pytest"


def test_an_ignored_venv_gives_no_warning(project, capsys):
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / ".gitignore").write_text(".venv/\n")
    (project / "requirements.txt").write_text("pytest\n")
    (project / "test_x.py").write_text("")
    _init(project)
    assert ".gitignore" not in capsys.readouterr().out


@pytest.mark.parametrize("given, expected", [
    ("python -m pytest", ".venv/bin/python -m pytest"),
    ("python3 -m pytest -q", ".venv/bin/python -m pytest -q"),
    ("pytest", ".venv/bin/pytest"),
    ("make test", "make test"),
])
def test_a_given_check_calls_the_venv_setup_makes(project, given, expected):
    (project / "requirements.txt").write_text("requests\n")
    assert _init(project, "--check", given).jobs["check"] == expected


def test_nothing_found_writes_nothing_and_says_what_to_do(project, capsys):
    assert cli.main(["init"]) == 2
    assert "--check" in capsys.readouterr().err
    assert list(project.iterdir()) == []


def test_check_option_is_the_gate(project):
    assert _init(project, "--check", "./ci.sh").jobs["check"] == "./ci.sh"


def test_never_replaces_a_file_without_force(project):
    (project / PROJECT_FILE).write_text("mine")
    assert cli.main(["init", "--check", "x"]) == 2
    assert (project / PROJECT_FILE).read_text() == "mine"
    assert _init(project, "--check", "x", "--force").jobs["check"] == "x"


def test_print_writes_nothing(project, capsys):
    assert cli.main(["init", "--check", "x", "--print"]) == 0
    assert "check: x" in capsys.readouterr().out
    assert list(project.iterdir()) == []


def test_a_worktree_is_named_after_its_repository(tmp_path, monkeypatch):
    main = tmp_path / "example-app"
    main.mkdir()
    commands = (["init", "-q"], ["-c", "user.name=a", "-c", "user.email=a@example.com", "commit",
                                 "-q", "--allow-empty", "-m", "x"],
                ["worktree", "add", "-q", str(tmp_path / "fix-the-login")])
    for command in commands:
        subprocess.run(["git", *command], cwd=main, check=True, capture_output=True)
    assert init_detect.project_name(tmp_path / "fix-the-login") == "example-app"
    assert init_detect.project_name(main) == "example-app"
    (main / "api").mkdir()
    assert init_detect.project_name(main / "api") == "api"


COMPOSE = """services:
  mysql:
    image: mysql:8.4
  api:
    build:
      context: ./api
  worker:
    build:
      context: ./api
"""


def _laravel_and_web(root):
    (root / "docker-compose.yml").write_text(COMPOSE)
    (root / "docker-compose.ci.yml").write_text("services:\n  mysql:\n    tmpfs: [/var/lib/mysql]\n")
    (root / "api").mkdir()
    (root / "api" / "composer.json").write_text(json.dumps({"require-dev": {"phpunit/phpunit": "^11"}}))
    (root / "api" / "artisan").write_text("<?php\n")
    (root / "web").mkdir()
    (root / "web" / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}))
    (root / "web" / "package-lock.json").write_text("{}")


def _workflow(root, text):
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text(text)


def test_php_built_by_a_service_installs_and_tests_in_it(project):
    _laravel_and_web(project)
    config = _init(project)
    assert config.install == "docker compose exec -T api composer install --no-interaction --prefer-dist"
    gate = config.jobs["check"]
    assert "docker compose exec -T api php artisan test" in gate and "cd api" not in gate
    assert "(cd web && npm run test)" in gate
    assert list(config.compose) == ["docker-compose.yml", "docker-compose.ci.yml"]  # overlay by name


def test_the_compose_files_ci_uses_win(project):
    _laravel_and_web(project)
    (project / "docker-compose.e2e.yml").write_text("services: {}\n")
    _workflow(project, "env:\n  COMPOSE_FILE: docker-compose.yml:docker-compose.e2e.yml\n"
                       "jobs: {}\n# COMPOSE_FILE: docker-compose.yml:missing.yml\n")
    assert list(_init(project).compose) == ["docker-compose.yml", "docker-compose.e2e.yml"]


@pytest.mark.parametrize(("local", "newest", "pinned"), [
    ("22.9.0", "24.22.2", "24.22.2"),   # this computer has another major: CI's newest
    ("24.1.0", "24.22.2", "24.1.0"),    # this computer has CI's major: that one
    ("22.9.0", None, None),             # offline: nothing pinned, the note says what to pin
])
def test_node_follows_ci_major(project, monkeypatch, capsys, local, newest, pinned):
    _package(project, scripts={"test": "vitest run"})
    (project / "package-lock.json").write_text("{}")
    _workflow(project, "steps:\n  - uses: actions/setup-node@v4\n    with:\n      node-version: '24'\n")
    monkeypatch.setattr(init_detect, "local_version", lambda tool: local)
    monkeypatch.setattr(init_ci, "newest_node", lambda major: newest if major == 24 else None)
    config = _init(project)
    assert dict(config.toolchain).get("node") == pinned
    if pinned is None:
        assert "pin an exact 24.x version" in capsys.readouterr().out
