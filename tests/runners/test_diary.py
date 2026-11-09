"""How a runner job went, from diaries laid out as the real runner writes them."""

from mulebox.common.protocol import Outcome
from mulebox.runners import diary

STAMP = "[2026-11-09 15:01:03Z INFO StepsRunner]"


def step(name, result=None, messages=(), state=None):
    lines = [f"{STAMP} Current state: job state = '{state}'"] if state else []
    lines.append(f"{STAMP} Processing step: DisplayName='{name}'")
    if result:
        quoted = ",\n".join(f'    "{text}"' for text in messages)
        lines += [f"{STAMP} Step result: {result}",
                  "[x INFO ExecutionContext] Publish step telemetry for current step {",
                  f'  "result": "{result.lower()}",',
                  '  "errorMessages": [' + (f"\n{quoted}\n  ]," if messages else "],"),
                  '  "executionTimeInSeconds": 82', "}."]
        if result != "Succeeded":
            lines.append(f"{STAMP} Update job result with current step result '{result}'.")
    else:
        lines.append(f"{STAMP} No need for updating job result with current step result 'Succeeded'.")
    return "\n".join(lines)


def hook(state):
    return f"{STAMP} Current state: job state = '{state}'\n{STAMP} Processing step: DisplayName='Complete runner'"


def test_a_job_whose_steps_all_passed_passed():
    text = "\n".join([step("Check out"), step("Run tests", state="Succeeded"), hook("Succeeded")])
    assert diary.job_result(text) == diary.JobResult(Outcome.PASSED)
    assert diary.job_result(text).fields() == {"outcome": "passed"}


def test_a_failed_job_names_its_first_failed_step_and_what_github_says():
    text = "\n".join([step("Check out"),
                      step("Concurrent frontend", "Failed", ["Process completed with exit code 1."]),
                      step("Logs on failure", state="Failed"), step("Tests", "Failed", ["later"]),
                      hook("Failed")])
    result = diary.job_result(text)
    assert result == diary.JobResult(Outcome.FAILED, "Concurrent frontend",
                                     "Process completed with exit code 1.")
    assert result.fields() == {"outcome": "failed", "step": "Concurrent frontend",
                               "message": "Process completed with exit code 1."}


def test_a_step_that_may_fail_does_not_fail_the_job():
    text = "\n".join([step("Optional lint", "Failed", ["exit 1"]).rsplit("\n", 1)[0],
                      f"{STAMP} No need for updating job result with current step result 'Failed'.",
                      step("Tests", state="Succeeded"), hook("Succeeded")])
    assert diary.job_result(text).outcome is Outcome.PASSED


def test_a_cancelled_job_and_a_diary_that_says_nothing():
    text = "\n".join([step("Run pnpm check", "Canceled", ["The operation was canceled."]),
                      hook("Canceled")])
    assert diary.job_result(text) == diary.JobResult(
        Outcome.CANCELLED, "Run pnpm check", "The operation was canceled.")
    assert diary.job_result(f"{STAMP} Processing step: DisplayName='Set up job'") is None
    assert diary.job_result("") is None


def test_the_newest_diary_is_read(tmp_path):
    diag = tmp_path / "runner" / "_diag"
    assert diary.read_result(tmp_path / "runner") is None
    diag.mkdir(parents=True)
    (diag / "Worker_20261109-145920-utc.log").write_text(hook("Failed"))
    (diag / "Worker_20261109-150954-utc.log").write_text(hook("Succeeded"))
    assert diary.newest(tmp_path / "runner").name == "Worker_20261109-150954-utc.log"
    assert diary.read_result(tmp_path / "runner").outcome is Outcome.PASSED
