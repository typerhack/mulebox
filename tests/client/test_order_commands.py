"""`mulebox queue rules` and `mulebox project priority` through the real coordinator code."""

import json

from mulebox import cli

from .test_detached import detach


def test_rules_show_set_and_reset(local, capsys):
    assert cli.main(["queue", "rules"]) == 0
    out = capsys.readouterr().out
    assert "first come, first served" in out and "fair turns between projects: off" in out
    assert cli.main(["queue", "rules", "--branch", "main=high", "--fair-turns", "on",
                     "--project", "example-app=-2", "--aging", "15"]) == 0
    out = capsys.readouterr().out
    assert "projects       example-app -2" in out and "branches       main +1" in out
    assert "+1 every 15 min in line" in out and "fair turns between projects: on" in out
    assert cli.main(["queue", "rules", "--json"]) == 0
    rules = json.loads(capsys.readouterr().out)["rules"]
    assert rules["branches"] == {"main": 1} and rules["fair_turns"] is True
    assert cli.main(["queue", "rules", "--reset"]) == 0
    assert "first come, first served" in capsys.readouterr().out


def test_a_bad_level_or_option_says_why(local, capsys):
    assert cli.main(["queue", "rules", "--github", "loud"]) == 4
    assert "github must be low, normal, high" in capsys.readouterr().err
    assert cli.main(["queue", "rules", "--project", "example-app"]) == 2
    assert "NAME=LEVEL" in capsys.readouterr().err
    assert cli.main(["queue", "rules", "--reset", "--aging", "5"]) == 2


def test_project_priority_and_the_reason_in_queue_and_status(local, in_project, capsys):
    job_id, _ = detach(capsys)
    assert cli.main(["project", "priority", "example-app"]) == 0
    assert capsys.readouterr().out.startswith("example-app\tlevel 0 (normal)")
    assert cli.main(["project", "priority", "example-app", "high"]) == 0
    assert capsys.readouterr().out.startswith("example-app\tlevel +1")
    assert cli.main(["status", job_id]) == 0
    assert "place: project example-app +1; then by arrival" in capsys.readouterr().out
    assert cli.main(["queue"]) == 0
    assert "  place: project example-app +1; then by arrival" in capsys.readouterr().out
