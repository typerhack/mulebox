import pytest

from mulebox.client.excludes import Excludes

SECRET = [
    ".env",
    ".env.local",
    "app/.env.production",
    ".secret/x",
    ".secret/deep/y",
    "a/secrets/b",
    "secrets/b",
    "id_ed25519",
    "id_ed25519.pub",
    "home/.ssh/id_rsa",
    "x.pem",
    "certs/server.key",
    ".npmrc",
    "pkg/.npmrc",
    ".mulebox/state",
    ".ENV",
    "X.PEM",
    ".env/inside",
]
KEPT = [
    "src/app.py",
    "env.txt",
    "environment.md",
    "secrets.md",
    "docs/secret.md",
    ".envrc",
    "keys.json",
    "pem.txt",
    "src/key.py",
    ".secretive",
]


@pytest.mark.parametrize("path", SECRET)
def test_builtin_excludes_secret_paths(path):
    assert Excludes().excluded(path)


@pytest.mark.parametrize("path", KEPT)
def test_builtin_keeps_ordinary_paths(path):
    assert not Excludes().excluded(path)


def test_directory_pattern_needs_a_directory():
    # `secrets/` names a directory; a file called `secrets` is a file, not secret by name.
    assert not Excludes().excluded("secrets")
    assert Excludes().excluded("secrets/a")


def test_project_excludes():
    excludes = Excludes(["reports/", "*.log", "docs/private/*", "/build/out.bin"])
    assert excludes.excluded("reports/today.html")
    assert excludes.excluded("sub/reports/x")
    assert excludes.excluded("a/b/debug.log")
    assert excludes.excluded("docs/private/notes.md")
    assert excludes.excluded("build/out.bin")
    assert not excludes.excluded("docs/public/notes.md")
    assert not excludes.excluded("reports.md")


def test_whole_path_pattern_excludes_directory_contents():
    assert Excludes(["vendor/big"]).excluded("vendor/big/file.bin")
    assert not Excludes(["vendor/big"]).excluded("other/vendor/big/file.bin")


def test_empty_patterns_are_ignored():
    excludes = Excludes(["", "/", "  "])
    assert not excludes.excluded("src/a.py")
