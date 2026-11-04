"""Jobs with their own `setup` and `compose` in `.mulebox.yml`."""

import pytest

from mulebox.common.config import ConfigError, load_project_config
from mulebox.common.config_jobs import for_job, port_variable

HEAD = """project: example-app
needs: [node]
compose: [docker-compose.yml]
setup: pnpm install
env:
  API: http://127.0.0.1:${MULEBOX_PORT_API_8000}
  HEALTH: ${API}/health
  CI: "1"
"""


def load(tmp_path, jobs, head=HEAD):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    path = tmp_path / ".mulebox.yml"
    path.write_text(head + "jobs:\n" + jobs)
    return load_project_config(path)


def test_plain_commands_mean_what_they_always_did(tmp_path):
    project = load(tmp_path, "  check: pnpm check\n  lint: pnpm lint\n")
    assert project.jobs == {"check": "pnpm check", "lint": "pnpm lint"}
    assert project.job_options == {}
    assert for_job(project, "lint") == (project, [])
    assert for_job(project, None) == (project, [])


def test_a_job_can_have_no_containers_and_its_own_setup(tmp_path):
    project = load(tmp_path, "  check: pnpm check\n  lint:\n    run: pnpm lint\n"
                             "    setup: pnpm install --offline\n    compose: false\n")
    assert project.jobs["lint"] == "pnpm lint"
    job, dropped = for_job(project, "lint")
    assert job.setup == "pnpm install --offline" and job.compose == ()
    assert job.all_needs == ("node",)
    assert job.env == {"CI": "1"} and dropped == ["API", "HEALTH"]  # also through an entry
    assert for_job(project, "check")[0].compose == ("docker-compose.yml",)


def test_setup_false_means_none_and_leaving_it_out_keeps_the_default(tmp_path):
    project = load(tmp_path, "  check: pnpm check\n  a:\n    run: x\n    setup: false\n"
                             "  b:\n    run: y\n    compose: true\n")
    assert for_job(project, "a")[0].setup is None
    job, dropped = for_job(project, "b")
    assert job.setup == "pnpm install" and job.compose and "API" in job.env and not dropped


def test_a_name_that_is_no_job_is_the_project_as_it_is(tmp_path):
    project = load(tmp_path, "  check: pnpm check\n")
    assert for_job(project, "run")[0] == project


def test_a_port_is_the_jobs_own(tmp_path):
    head = 'project: example-app\nenv:\n  URL: "http://127.0.0.1:${MULEBOX_PORT_VITE}"\n'
    project = load(tmp_path, "  check: pnpm check\n  e2e:\n    run: x\n    ports: [vite, my-api]\n",
                   head)
    job, dropped = for_job(project, "e2e")
    assert job.host_ports == ("vite", "my-api") and not dropped
    assert port_variable("my-api") == "MULEBOX_PORT_MY_API"
    assert for_job(project, "check")[1] == ["URL"]
    assert for_job(project, None)[1] == ["URL"]


@pytest.mark.parametrize("name", ["api_8000", "API-8000", "x_53_udp", "2fast", "a b", "a,b"])
def test_a_name_that_could_be_a_service_port_or_break_the_list_is_refused(tmp_path, name):
    with pytest.raises(ConfigError, match="ports"):
        load(tmp_path, f'  check:\n    run: x\n    ports: ["{name}"]\n')


def test_the_same_port_twice_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="twice"):
        load(tmp_path, "  check:\n    run: x\n    ports: [a-b, a_b]\n")


@pytest.mark.parametrize("jobs, field", [
    ("  check:\n    setup: x\n", "jobs.check.run"),
    ("  check:\n    run: x\n    compose: nope\n", "jobs.check.compose"),
    ("  check:\n    run: x\n    setup: true\n", "jobs.check.setup"),
    ("  check:\n    run: x\n    other: 1\n", "jobs.check.other"),
    ("  check: 1\n", "jobs.check"),
    ("  lint: x\n", "jobs"),
])
def test_mistakes_name_the_field(tmp_path, jobs, field):
    with pytest.raises(ConfigError, match=field):
        load(tmp_path, jobs)
