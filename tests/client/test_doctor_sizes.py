"""`mulebox doctor` on declared sizes beside measured ones (client/doctor_sizes.py)."""

from mulebox.client import doctor_sizes
from mulebox.common.config import ProjectConfig
from mulebox.common.config_jobs import JobOptions

GB = 10**9


def usage(job="check", measured=5, cores=6.2, memory=3 * GB):
    return {"jobs": [{"job": job, "kind": "job", "measured": measured,
                      "cores": {"median": cores - 1, "max": cores},
                      "memory": {"median": memory, "max": memory},
                      "fits": {"cores": 7, "memory": memory}}]}


def project(size=None, e2e=None):
    return ProjectConfig("example-app", {"check": "make", "e2e": "make e2e"}, size=size,
                         job_options={"e2e": JobOptions(size=e2e)} if e2e else {})


def test_a_job_that_used_more_than_it_asks_is_warned():
    found = doctor_sizes.findings(project({"cores": 4.0}), usage())
    assert len(found) == 1 and found[0].level == "warn"
    assert "asks for 4.0 cores but used up to 6.2 cores" in found[0].text
    assert "fit 7 cores and 3.0 GB" in found[0].text


def test_a_job_that_asks_far_more_than_it_uses_is_warned():
    found = doctor_sizes.findings(project({"memory": 16 * GB}), usage())
    assert "keeps room other jobs could use" in found[0].text


def test_a_close_size_an_unsized_job_and_few_runs_say_nothing():
    assert doctor_sizes.findings(project({"cores": 7.0, "memory": 4 * GB}), usage()) == []
    assert doctor_sizes.findings(project(e2e={"cores": 1.0}), usage()) == []
    assert doctor_sizes.findings(project({"cores": 1.0}), usage(measured=2)) == []
    assert doctor_sizes.findings(project({"cores": 1.0}), None) == []
