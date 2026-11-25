"""Job sizes (common/job_size.py): what a size is, a node's budget and what fits."""

import pytest

from mulebox.common import job_size
from mulebox.common.job_size import Budget

GB = 10**9


def test_a_size_from_a_config_or_the_wire():
    assert job_size.checked({"cores": 4, "memory": "6GB"}) == {"cores": 4.0, "memory": 6 * GB}
    assert job_size.checked({"memory": 512 * 10**6}) == {"memory": 512 * 10**6}
    assert job_size.checked({"cores": 0.5}) == {"cores": 0.5}
    assert job_size.checked(None) is None
    for bad in ({"cores": 0}, {"cores": True}, {"memory": "6 apples"}, {"gpus": 1}, {}, "4"):
        with pytest.raises(ValueError):
            job_size.checked(bad)


def test_the_budget_is_the_node_less_what_its_owner_keeps():
    load = {"cores": 8, "memory": {"total": 16 * GB}}
    assert job_size.budget(load, {}, 2) == Budget(8.0, 16 * GB, 2)
    kept = job_size.budget(load, {"keep_cores": 2, "keep_memory": "4GB"}, 2)
    assert kept == Budget(6.0, 12 * GB, 2) and kept.share() == {"cores": 3.0, "memory": 6 * GB}
    assert job_size.budget({}, {}, 2) is None and job_size.budget(load, {}, None) is None


def test_jobs_with_no_size_fill_the_slots_exactly_as_before():
    node = Budget(8.0, 16 * GB, 3)  # shares that do not divide evenly still fit three times
    assert job_size.fits(node, [None, None], None)
    assert not job_size.fits(node, [None, None, None], None)


def test_sized_jobs_share_the_budget():
    node = Budget(8.0, 16 * GB, 2)
    assert job_size.fits(node, [{"cores": 6, "memory": 2 * GB}], {"cores": 2, "memory": 2 * GB})
    assert not job_size.fits(node, [{"cores": 6}], None)  # one slot's share is 4 cores
    assert not job_size.fits(node, [], {"cores": 4, "memory": 20 * GB})
    assert node.holds({"cores": 8}) and not node.holds({"cores": 9})
    assert job_size.room_words(node, [{"cores": 6, "memory": 2 * GB}]) == "2 cores and 14.0 GB free"
