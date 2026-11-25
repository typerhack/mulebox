"""`mulebox usage`: the table, one run, and what is sent."""

import argparse

from mulebox.client import usage_commands as uc

GB = 1_000_000_000


def args(**given):
    base = {"job_id": None, "project": None, "job": None, "machine": None, "kind": None,
            "runs": 20, "all": False}
    return argparse.Namespace(**{**base, **given})


def test_the_body_names_only_what_was_asked():
    assert uc.body(args()) == {"runs": 20}
    assert uc.body(args(kind="ci", machine="build-1", all=True, runs=0)) == {
        "kind": "runner", "worker": "build-1", "runs": 1, "all": True}
    assert uc.body(args(job_id="job-a", project="x")) == {"job_id": "job-a"}


def test_the_table_reads_median_peak_and_fit():
    found = {"runs": 20, "all": False, "machines": {"build-1": {"cores": 8, "memory": 16 * GB}},
             "jobs": [{"project": "example-app", "job": "check", "kind": "job", "runs": 4,
                       "measured": 3, "not_measured": 1, "cores": {"median": 2.0, "max": 3.4},
                       "memory": {"median": GB, "max": 2.1 * GB},
                       "fits": {"cores": 4, "memory": 2.5 * GB}},
                      {"project": "example-app", "job": "test", "kind": "runner", "runs": 1,
                       "measured": 0, "not_measured": 1, "cores": None, "memory": None,
                       "fits": None}]}
    text = "\n".join(uc.render_jobs(found))
    assert "3 of 4" in text and "2.0 / 3.4" in text and "1.0 GB / 2.1 GB" in text
    assert "4 cores, 2.5 GB" in text and "GitHub" in text
    assert "machines: build-1 8 cores, 16.0 GB" in text and "older node" in text
    assert uc.render_jobs({"jobs": [], "all": True}) == ["No finished run fits these filters yet."]


def test_one_runs_line():
    usage = {"peak_cores": 6.1, "peak_cores_stage": "command", "peak_memory": 3 * GB,
             "peak_memory_stage": "setup", "cpu_s": 100.0, "samples": 9}
    assert uc.peaks_line(usage, 1.25) == ("peak 6.1 cores in command, peak 3.0 GB memory in "
                                          "setup, average 1.2 cores")
    assert uc.peaks_line({"peak_cores": None, "peak_memory": 10**6, "samples": 1}) == (
        "cores: too short to measure, peak 1.0 MB memory")
    assert uc.peaks_line(None).startswith("not measured")
