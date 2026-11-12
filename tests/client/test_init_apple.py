"""`mulebox init` for Apple platforms (client/init_apple.py): Xcode workspaces and projects,
Swift packages. The project files are the shapes Xcode writes, cut to what is read."""

import plistlib

import pytest

from mulebox import cli
from mulebox.client import init_ci, init_detect
from mulebox.common.config import PROJECT_FILE, load_project_config
from mulebox.worker import xcode


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "ExampleApp"
    root.mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setattr(init_detect, "local_version", lambda tool: None)
    monkeypatch.setattr(init_ci, "newest_node", lambda major: None)
    return root


def _xcode_here(tmp_path, monkeypatch, version="16.2"):
    app = tmp_path / "Applications" / "Xcode.app"
    (app / "Contents" / "Developer").mkdir(parents=True)
    (app / "Contents" / "version.plist").write_bytes(
        plistlib.dumps({"CFBundleShortVersionString": version}))
    monkeypatch.setattr(xcode, "SELECTED", lambda: app)


def _xcodeproj(root, name, sdk_lines, schemes=("ExampleApp",)):
    bundle = root / f"{name}.xcodeproj"
    bundle.mkdir()
    (bundle / "project.pbxproj").write_text(
        "// !$*UTF8*$!\n{\n\tobjects = {\n" + "".join(f"\t\t\t\t{line}\n" for line in sdk_lines)
        + "\t};\n}\n")
    folder = bundle / "xcshareddata" / "xcschemes"
    folder.mkdir(parents=True)
    for scheme in schemes:
        (folder / f"{scheme}.xcscheme").write_text("<Scheme/>")
    return bundle


def _init(root):
    assert cli.main(["init"]) == 0
    return load_project_config(root / PROJECT_FILE)


def test_an_ios_app_tests_in_its_own_simulator_with_the_xcode_of_this_computer(
        project, tmp_path, monkeypatch):
    _xcode_here(tmp_path, monkeypatch)
    _xcodeproj(project, "ExampleApp", ["SDKROOT = iphoneos;"], ("ExampleApp", "ExampleAppUI"))
    config = _init(project)
    assert config.toolchain == {"xcode": "16.2"}
    assert config.needs == ("cache-spm", "simulator")
    assert config.jobs["check"] == (
        'xcodebuild test -project ExampleApp.xcodeproj -scheme ExampleApp -destination '
        '"id=$MULEBOX_SIMULATOR" -derivedDataPath "$MULEBOX_DERIVED_DATA" '
        '-packageCachePath "$MULEBOX_CACHE_SPM" CODE_SIGNING_ALLOWED=NO')
    text = (project / PROJECT_FILE).read_text()
    assert "other shared schemes: ExampleAppUI" in text and "pinned 16.2" in text


def test_a_workspace_with_pods_and_a_multiplatform_target(project, tmp_path, monkeypatch):
    _xcode_here(tmp_path, monkeypatch)
    _xcodeproj(project, "ExampleApp", ['SDKROOT = auto;',
                                       'SUPPORTED_PLATFORMS = "iphoneos iphonesimulator macosx";'])
    (project / "ExampleApp.xcworkspace").mkdir()  # pod install makes it, shares the project's
    (project / "Podfile").write_text("platform :ios, '17.0'\n")
    config = _init(project)
    assert config.setup == "pod install"
    assert "-workspace ExampleApp.xcworkspace" in config.jobs["check"]
    assert set(config.needs) == {"cache-spm", "cache-cocoapods", "simulator"}


def test_a_mac_app_tests_on_the_mac(project, tmp_path, monkeypatch):
    _xcode_here(tmp_path, monkeypatch)
    _xcodeproj(project, "ExampleApp", ["SDKROOT = macosx;"])
    config = _init(project)
    assert "-destination platform=macOS" in config.jobs["check"]
    assert "simulator" not in config.needs


def test_a_swift_package(project):
    (project / "Package.swift").write_text("// swift-tools-version: 6.0\n")
    config = _init(project)
    assert config.jobs["check"] == 'swift test --cache-path "$MULEBOX_CACHE_SPM"'
    assert config.needs == ("cache-spm",) and config.toolchain == {}  # no Xcode here
    assert "none is pinned" in (project / PROJECT_FILE).read_text()


def test_no_shared_scheme_means_no_check(project, tmp_path, monkeypatch, capsys):
    _xcodeproj(project, "ExampleApp", ["SDKROOT = iphoneos;"], schemes=())
    assert cli.main(["init"]) == 2
    assert not (project / PROJECT_FILE).exists()


def test_a_package_beside_a_project_with_no_shared_scheme_is_tested_as_a_package(project):
    _xcodeproj(project, "Legacy", ["SDKROOT = macosx;"], schemes=())
    (project / "Package.swift").write_text("// swift-tools-version: 6.0\n")
    assert _init(project).jobs["check"].startswith("swift test")


def test_pods_before_their_workspace_exists_still_test_the_workspace(project):
    _xcodeproj(project, "ExampleApp", ["SDKROOT = iphoneos;"])
    (project / "Podfile").write_text("platform :ios, '17.0'\n")  # a fresh checkout: no workspace
    config = _init(project)
    assert "-workspace ExampleApp.xcworkspace -scheme ExampleApp" in config.jobs["check"]


def test_a_workspace_reads_the_projects_it_lists(project):
    nested = project / "App"
    nested.mkdir()
    _xcodeproj(nested, "App", ["SDKROOT = iphoneos;"], ("App",))
    workspace = project / "Example.xcworkspace"
    workspace.mkdir()
    (workspace / "contents.xcworkspacedata").write_text(
        '<Workspace version = "1.0">\n<FileRef location = "group:App/App.xcodeproj">'
        "</FileRef>\n</Workspace>\n")
    config = _init(project)
    assert "-workspace Example.xcworkspace -scheme App" in config.jobs["check"]
    assert '"id=$MULEBOX_SIMULATOR"' in config.jobs["check"]  # the nested project is for iOS


def test_a_watch_app_is_told_to_pin_its_runtime(project):
    _xcodeproj(project, "ExampleApp", ["SDKROOT = watchos;"])
    _init(project)
    assert "the targets build for watchOS; pin its runtime" in (project / PROJECT_FILE).read_text()


def test_a_native_folder_beside_a_found_gate_is_named(project):
    (project / "package.json").write_text('{"scripts": {"test": "jest"}}')
    (project / "package-lock.json").write_text("{}")
    (project / "ios").mkdir()
    _xcodeproj(project / "ios", "App", ["SDKROOT = iphoneos;"])
    _init(project)
    assert "ios/ has an Xcode project, not in the gate" in (project / PROJECT_FILE).read_text()
