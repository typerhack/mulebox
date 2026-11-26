"""A job's kept files through the real worker loop (agent_files.py), with real job processes."""

import io
import tarfile

from mulebox.common.protocol import MessageType

from .fakes import claim_body
from .test_agent import agent, clock, executor, run_until  # noqa: F401

SHOTS = "mkdir -p shots/a && printf png > shots/a/one.png && printf two > shots/two.png"


def job(fake_link, command, keep=("shots/",)):
    body = {**claim_body(["bash", "-c", command]), "keep_files": list(keep)}
    fake_link.claims.append(body)
    return body["job_id"]


def result(fake_link):
    run_until_result = fake_link.of_type(MessageType.RESULT)
    return run_until_result[0].body if run_until_result else None


def finished(agent, fake_link):
    run_until(agent, lambda: result(fake_link) is not None)
    return result(fake_link)


def test_a_failed_job_keeps_its_files_and_says_how_to_fetch_them(agent, fake_link):
    job_id = job(fake_link, f"{SHOTS}; exit 3")
    said = finished(agent, fake_link)
    assert (said["outcome"], said["exit_code"]) == ("failed", 3)
    assert said["files"] == {"count": 2, "bytes": 6, "left_out": [], "left_out_count": 0,
                             "packed": True}
    data, sha = fake_link.packs[job_id]
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        assert sorted(tar.getnames()) == ["shots/a/one.png", "shots/two.png"]
    assert len(sha) == 64
    assert f"mulebox fetch {job_id}" in fake_link.log_text()
    assert not list((agent.paths.staging / "files-out").iterdir())  # the pack is not kept here


def test_a_passed_job_keeps_them_too_and_names_what_matched_nothing(agent, fake_link):
    job(fake_link, SHOTS, keep=("shots/", "coverage/"))
    said = finished(agent, fake_link)
    assert said["outcome"] == "passed" and said["files"]["count"] == 2
    assert said["files"]["left_out"] == ["coverage/: matches nothing"]
    assert "not kept: coverage/: matches nothing" in fake_link.log_text()


def test_nothing_found_sends_no_pack(agent, fake_link):
    job_id = job(fake_link, "true")
    said = finished(agent, fake_link)
    assert said["files"]["packed"] is False and said["files"]["count"] == 0
    assert job_id not in getattr(fake_link, "packs", {})


def test_a_lost_link_sends_the_pack_once_it_is_back(agent, fake_link):
    job_id = job(fake_link, SHOTS)
    run_until(agent, lambda: any(j.files_stage == "packing" for j in agent.finishing))
    fake_link.down = True
    for _ in range(5):
        agent.step()
    assert result(fake_link) is None  # the result waits for the files
    fake_link.down = False
    said = finished(agent, fake_link)
    assert said["files"]["packed"] is True and job_id in fake_link.packs


def test_a_refused_pack_is_not_sent_again_and_the_log_says_why(agent, fake_link):
    fake_link.refuse.add(MessageType.STATUS_OK)
    job(fake_link, SHOTS)
    said = finished(agent, fake_link)
    assert said["files"]["packed"] is False
    assert "did not reach the coordinator: no (fake)" in fake_link.log_text()


def test_a_job_whose_command_never_started_keeps_nothing(agent, fake_link):
    body = {**claim_body(["bash", "-c", SHOTS], setup="exit 9"), "keep_files": ["shots/"]}
    fake_link.claims.append(body)
    said = finished(agent, fake_link)
    assert "files" not in said
