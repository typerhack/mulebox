"""The upgrade command named in messages follows how mulebox was installed."""

from mulebox.common import upgrade


def test_the_command_follows_the_installer():
    assert upgrade.command("/home/alice/.local/share/pipx/venvs/mulebox") == upgrade.PIPX
    assert upgrade.command("/home/alice/.local/pipx/venvs/mulebox") == upgrade.PIPX
    assert upgrade.command("/home/alice/.local/share/uv/tools/mulebox") == upgrade.UV
    assert upgrade.command("/home/alice/.mulebox-client") == upgrade.EITHER


def test_both_name_pypi_s_package():
    for text in (upgrade.PIPX, upgrade.UV, upgrade.EITHER):
        assert "upgrade mulebox" in text
