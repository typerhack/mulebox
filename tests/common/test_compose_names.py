"""Names and filters derived from a job id: the base of every Docker cleanup."""

import re

import pytest

from mulebox.common import compose
from mulebox.common.package_cache import CAPABILITIES as PACKAGE_CACHES
from mulebox.common.ids import new_id

BAD_IDS = ["", "job", "job-", "job-short", "*", "job-*", "../job", "att-" + "0" * 26,
           "job-01M6JW0YXQ5TASH2X7D95J4H8Z,label=x", "job-01m6jw0yxq5tash2x7d95j4h8z"]


def test_project_name_is_a_valid_compose_name_and_keeps_the_job_apart():
    one, two = new_id("job"), new_id("job")
    assert re.fullmatch(r"[a-z0-9][a-z0-9_-]*", compose.project_name(one))
    assert compose.project_name(one) != compose.project_name(two)
    assert compose.project_name(one).endswith(one.lower())


def test_filters_name_one_exact_job():
    job_id = new_id("job")
    assert compose.job_filter(job_id) == f"label=mulebox.job={job_id}"
    assert compose.project_filter(job_id) == (
        f"label=com.docker.compose.project=mulebox-{job_id.lower()}")


@pytest.mark.parametrize("job_id", BAD_IDS)
@pytest.mark.parametrize("make", [compose.project_name, compose.job_filter, compose.project_filter])
def test_nothing_is_derived_from_a_bad_id(make, job_id):
    with pytest.raises(compose.ComposeError):
        make(job_id)


def test_file_list_round_trip():
    files = ("docker-compose.yml", "ci/docker-compose.ci.yml")
    assert compose.split_files(compose.join_files(files)) == files


@pytest.mark.parametrize("value", ["../a.yml", "/etc/a.yml", "a.yml:/etc/b.yml", "a b.yml", ""])
def test_a_tampered_file_list_is_refused(value):
    with pytest.raises(compose.ComposeError):
        compose.split_files(value)


def test_a_worker_reports_compose_by_itself_only_with_docker():
    assert compose.worker_capabilities(("docker", "node")) == [
        "docker", "node", "compose-v1", *PACKAGE_CACHES]
    assert compose.worker_capabilities(("node",)) == ["node", *PACKAGE_CACHES]
    assert compose.worker_capabilities(()) == [*PACKAGE_CACHES]


def test_saying_it_twice_changes_nothing():
    assert compose.worker_capabilities(("docker", "compose-v1")) == [
        "docker", "compose-v1", *PACKAGE_CACHES]
