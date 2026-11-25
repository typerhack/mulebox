"""The runner version is asked of GitHub once a day per node, and a failed ask keeps the last."""

import pytest

from mulebox.runners import release, runner_version

DAY = runner_version.FRESH_S


def asker(*answers):
    asked = []

    def ask():
        asked.append(1)
        answer = answers[len(asked) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer
    return ask, asked


def test_kept_for_a_day_then_asked_again(paths):
    ask, asked = asker("2.330.0", "2.331.0")
    assert runner_version.known(paths, ask, clock=lambda: 1000.0) == "2.330.0"
    assert runner_version.known(paths, ask, clock=lambda: 1000.0 + DAY - 1) == "2.330.0"
    assert len(asked) == 1  # a restart, or another place, does not ask again
    assert runner_version.known(paths, ask, clock=lambda: 1000.0 + DAY + 1) == "2.331.0"


def test_a_failed_ask_keeps_the_last_version(paths):
    ask, _ = asker("2.330.0", release.ReleaseError("rate limit exceeded"))
    runner_version.known(paths, ask, clock=lambda: 0.0)
    assert runner_version.known(paths, ask, clock=lambda: 3 * DAY) == "2.330.0"


def test_with_nothing_kept_a_failed_ask_fails(paths):
    ask, _ = asker(release.ReleaseError("rate limit exceeded"))
    with pytest.raises(release.ReleaseError):
        runner_version.known(paths, ask)


def test_with_nothing_kept_the_newest_built_image_stands_in(paths):
    ask, _ = asker(release.ReleaseError("rate limit exceeded"))
    assert runner_version.known(paths, ask, built=lambda: "2.329.0") == "2.329.0"


def test_newest_built_takes_only_images_of_todays_recipe():
    from mulebox.runners import place_image

    class Docker:
        def lines(self, *args):
            good = [place_image.tag(v).partition(":")[2] for v in ("2.329.0", "2.330.0")]
            return [*good, "2.999.0-oldrecipe1234"]
    assert place_image.newest_built(Docker()) == "2.330.0"
