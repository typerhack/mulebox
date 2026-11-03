"""Release lookup, checksum parsing, verified download and cache. No network."""

import pytest

from mulebox.runners import release
from mulebox.runners.release import ReleaseError

from .conftest import VERSION, release_body, release_json

SHA = "ab" * 32


def test_parse_release_picks_linux_x64_asset_and_checksum():
    found = release.parse_release(release_json(SHA), "x64")
    assert found.version == VERSION
    assert found.asset == f"actions-runner-linux-x64-{VERSION}.tar.gz"
    assert found.url == ("https://github.com/actions/runner/releases/download/"
                         f"v{VERSION}/actions-runner-linux-x64-{VERSION}.tar.gz")
    assert found.sha256 == SHA


def test_parse_release_arm64():
    found = release.parse_release(release_json(SHA, "cd" * 32), "arm64")
    assert found.asset == f"actions-runner-linux-arm64-{VERSION}.tar.gz"
    assert found.sha256 == "cd" * 32


def test_body_sha_ignores_variant_markers():
    body = release_body(SHA, "cd" * 32)
    assert release.body_sha(body, "x64") == SHA  # not the linux-x64_noexternals entry
    assert release.body_sha(body.replace(SHA, SHA.upper()), "x64") == SHA


@pytest.mark.parametrize("change", [
    lambda d: d.update(body="no checksums here"),
    lambda d: d.update(assets=[]),
    lambda d: d.update(tag_name="latest"),
    lambda d: d["assets"][1].update(browser_download_url="https://evil.example/x.tar.gz"),
])
def test_parse_release_refuses_incomplete_releases(change):
    data = release_json(SHA)
    change(data)
    with pytest.raises(ReleaseError):
        release.parse_release(data, "x64")


def test_unknown_arch_refused():
    with pytest.raises(ReleaseError, match="linux-s390x"):
        release.parse_release(release_json(SHA), "s390x")


def test_latest_release_asks_the_releases_latest_endpoint():
    urls = []
    found = release.latest_release("x64", lambda url: urls.append(url) or release_json(SHA))
    assert urls == ["https://api.github.com/repos/actions/runner/releases/latest"]
    assert found.sha256 == SHA


def test_fetch_verified_downloads_and_caches(paths, fakes):
    found = release.parse_release(release_json(fakes.sha), "x64")
    path = release.fetch_verified(paths, found, fakes.fetch_file)
    assert path == paths.cache / "actions-runner" / found.asset
    again = release.fetch_verified(paths, found, fakes.fetch_file)
    assert again == path and len(fakes.downloads) == 1


def test_checksum_mismatch_is_refused_and_nothing_is_kept(paths, fakes):
    found = release.parse_release(release_json("0" * 64), "x64")
    with pytest.raises(ReleaseError, match="does not match"):
        release.fetch_verified(paths, found, fakes.fetch_file)
    assert list((paths.cache / "actions-runner").iterdir()) == []


def test_corrupted_cache_is_downloaded_again(paths, fakes):
    found = release.parse_release(release_json(fakes.sha), "x64")
    path = release.fetch_verified(paths, found, fakes.fetch_file)
    path.write_bytes(b"tampered")
    assert release.fetch_verified(paths, found, fakes.fetch_file) == path
    assert path.read_bytes() == fakes.tarball.read_bytes()
    assert len(fakes.downloads) == 2


def test_extract_unpacks_into_the_runners_root(paths, tarball):
    dest = release.extract(paths, tarball, paths.runners / "build-1-example-app")
    assert (dest / "config.sh").is_file() and (dest / "bin" / "Runner.Listener").is_file()
