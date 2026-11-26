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


def test_kind_names_each_install_and_maps_back():
    assert upgrade.kind("/home/alice/.local/share/pipx/venvs/mulebox") == "pipx"
    assert upgrade.kind("/home/alice/.local/share/uv/tools/mulebox") == "uv"
    assert upgrade.kind("/home/alice/.mulebox-client") == "other"
    assert {upgrade.for_kind(k) for k in upgrade.KINDS} == {upgrade.CHECKOUT, upgrade.PIPX,
                                                             upgrade.UV, upgrade.EITHER}
    assert upgrade.for_kind(None) == upgrade.EITHER
