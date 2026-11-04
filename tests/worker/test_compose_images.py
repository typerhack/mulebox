"""Built images belong to one job: their tags, and the services that use them."""

from pathlib import Path

from mulebox.common import compose
from mulebox.worker.compose_file import rewrite

JOB_ID = "job-01M6JW0YXQ5TASH2X7D95J4H8Z"
PROJECT = compose.project_name(JOB_ID)
LABELS = {"mulebox.job": JOB_ID, "mulebox.worker": "build-1"}


def model(**service):
    return {"name": PROJECT, "services": {"api": {"image": "redis:7-alpine", **service}}}


def run(data):
    return rewrite(data, JOB_ID, LABELS, {}, Path("/jobs/app/job/src"))


def built(**service):
    return {"build": {"context": "/jobs/app/job/src"}, **service}


def test_a_built_image_with_a_tag_of_its_own_gets_one_only_this_job_has():
    result, notes = run(model(**built(image="example-app:ci")))
    tag = result["services"]["api"]["image"]
    assert tag.startswith(f"{PROJECT}-") and "example-app" not in tag
    assert any("example-app:ci" in note for note in notes)
    assert compose.owns_image(JOB_ID, f"{tag}:latest")


def test_a_built_image_without_a_tag_gets_one_too():
    data = model(**built())
    del data["services"]["api"]["image"]
    result, _ = run(data)
    assert compose.owns_image(JOB_ID, result["services"]["api"]["image"])


def test_extra_build_tags_go():
    data = model(**built())
    data["services"]["api"]["build"]["tags"] = ["example-app:ci", "registry.example/app:1"]
    result, _ = run(data)
    assert "tags" not in result["services"]["api"]["build"]


def test_a_service_using_a_built_image_follows_the_new_tag():
    data = model(**built(image="example-app:ci"))
    data["services"]["worker"] = {"image": "example-app:ci"}
    data["services"]["web"] = {"image": "example-app"}
    data["services"]["db"] = {"image": "mysql:8.4"}
    result, _ = run(data)
    services = result["services"]
    assert services["worker"]["image"] == services["api"]["image"]
    assert services["web"]["image"] == "example-app"  # another tag of the name, not this one
    assert services["db"]["image"] == "mysql:8.4"


def test_latest_is_the_same_image_as_no_tag():
    data = model(**built(image="example-app"))
    data["services"]["worker"] = {"image": "example-app:latest"}
    result, _ = run(data)
    assert result["services"]["worker"]["image"] == result["services"]["api"]["image"]


def test_two_builds_of_one_tag_share_the_jobs_tag():
    data = model(**built(image="example-app:ci"))
    data["services"]["worker"] = built(image="example-app:ci")
    result, _ = run(data)
    assert result["services"]["worker"]["image"] == result["services"]["api"]["image"]


def test_services_that_differ_only_in_punctuation_get_different_tags():
    data = model(**built())
    data["services"]["a.pi"] = built()
    data["services"]["A-pi"] = built()
    result, _ = run(data)
    tags = [spec["image"] for spec in result["services"].values()]
    assert len(set(tags)) == 3 and all(tag == tag.lower() for tag in tags)


def test_two_jobs_with_one_compose_file_do_not_share_a_tag():
    data = model(**built(image="example-app:ci"))
    first, _ = rewrite(data, JOB_ID, LABELS, {}, Path("/c"))
    second, _ = rewrite(data, "job-01M6JW0YXQ5TASH2X7D95J4H90", LABELS, {}, Path("/c"))
    assert first["services"]["api"]["image"] != second["services"]["api"]["image"]


def test_an_image_that_is_only_pulled_keeps_its_tag():
    result, _ = run(model(image="redis:7-alpine"))
    assert result["services"]["api"]["image"] == "redis:7-alpine"
