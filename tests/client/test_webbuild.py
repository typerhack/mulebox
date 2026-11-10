"""The web build before a wheel: only from a checkout, only when stale, and a stale or missing
build with no npm stops rather than ship a wheel with no page (with a stand-in for npm;
nothing here runs Node)."""

import os
import subprocess

import pytest

from mulebox.client import webbuild


def checkout(tmp_path):
    package = tmp_path / "mulebox"
    web = tmp_path / "web"
    (web / "src").mkdir(parents=True)
    (package / "dashboard").mkdir(parents=True)
    (web / "package.json").write_text("{}")
    (web / "src" / "main.tsx").write_text("export {};")
    return package, web


class Npm:
    """Stands in for npm: writes the build's index.html, or fails."""

    def __init__(self, package, fails=False):
        self.calls, self.package, self.fails = [], package, fails

    def __call__(self, command, **options):
        self.calls.append((command[1:], options["cwd"].name))
        if self.fails:
            raise subprocess.CalledProcessError(1, command, stderr="error TS1: broken\n")
        if command[1:] == ["run", "build"]:
            out = self.package / "dashboard" / "app"
            out.mkdir(exist_ok=True)
            (out / "index.html").write_text("<!doctype html>")


def found(name):
    return "/usr/bin/npm"


def test_a_pip_install_has_no_web_folder_and_nothing_runs(tmp_path):
    npm = Npm(tmp_path)
    assert webbuild.ensure(tmp_path / "site-packages" / "mulebox", which=found, run=npm) == "absent"
    assert not npm.calls


def no_npm(name):
    return None


def test_a_missing_build_without_npm_stops_and_says_how_to_get_node(tmp_path):
    package, _ = checkout(tmp_path)
    with pytest.raises(webbuild.WebBuildError, match="not built and npm is not on the PATH") as err:
        webbuild.ensure(package, which=no_npm, run=Npm(package))
    assert "Install Node.js" in str(err.value) and "npm run build" in str(err.value)


def test_a_stale_build_without_npm_stops_too(tmp_path):
    package, web = checkout(tmp_path)
    webbuild.ensure(package, which=found, run=Npm(package))
    index = package / "dashboard" / "app" / "index.html"
    later = index.stat().st_mtime + 10
    os.utime(web / "src" / "main.tsx", (later, later))
    with pytest.raises(webbuild.WebBuildError, match="out of date and npm is not on the PATH"):
        webbuild.ensure(package, which=no_npm)


def test_a_fresh_build_needs_no_npm(tmp_path):
    package, _ = checkout(tmp_path)
    webbuild.ensure(package, which=found, run=Npm(package))
    npm = Npm(package)
    assert webbuild.ensure(package, which=no_npm, run=npm) == "fresh"
    assert not npm.calls


def test_a_missing_build_installs_packages_once_and_builds(tmp_path):
    package, web = checkout(tmp_path)
    npm = Npm(package)
    assert webbuild.ensure(package, which=found, run=npm) == "built"
    assert npm.calls == [(["ci", "--no-audit", "--no-fund"], "web"), (["run", "build"], "web")]
    (web / "node_modules").mkdir()
    assert webbuild.ensure(package, which=found, run=npm) == "fresh"
    assert len(npm.calls) == 2


def test_a_newer_source_file_builds_again_without_installing(tmp_path):
    package, web = checkout(tmp_path)
    npm = Npm(package)
    webbuild.ensure(package, which=found, run=npm)
    (web / "node_modules").mkdir()
    index = package / "dashboard" / "app" / "index.html"
    later = index.stat().st_mtime + 10
    os.utime(web / "src" / "main.tsx", (later, later))
    assert webbuild.stale(web, index.parent)
    assert webbuild.ensure(package, which=found, run=npm) == "built"
    assert npm.calls[-1] == (["run", "build"], "web") and len(npm.calls) == 3
    os.utime(web / "package.json", (later + 10, later + 10))
    assert webbuild.stale(web, index.parent)


def test_a_failed_build_stops_with_the_last_lines(tmp_path):
    package, web = checkout(tmp_path)
    (web / "node_modules").mkdir()
    with pytest.raises(webbuild.WebBuildError, match="error TS1: broken"):
        webbuild.ensure(package, which=found, run=Npm(package, fails=True))
