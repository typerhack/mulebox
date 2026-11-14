"""What the client puts in a job's env beside the project's values (client/job_body.py)."""

from mulebox.client import job_body
from mulebox.common import isolation
from mulebox.common.config import ProjectConfig


def test_an_isolated_jobs_own_image_travels_in_its_env():
    project = ProjectConfig("example-app", {"check": "make"}, isolation="container",
                            image="ghcr.io/example/ci:1", env={"CI": "1"})
    assert job_body.job_env(project) == {"CI": "1", isolation.IMAGE_KEY: "ghcr.io/example/ci:1"}
    assert isolation.IMAGE_KEY not in job_body.job_env(ProjectConfig("example-app", {}))
