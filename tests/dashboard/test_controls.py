"""A job's and a machine's controls on the dashboard (dashboard/controls.py, M14.3)."""

from mulebox.client.remote import CoordinatorError
from mulebox.dashboard.cancel import TOKEN_HEADER

from .conftest import FakeCanceller


async def _token(http, url):
    return (await (await http.get(f"{url}/api/session")).json())["action_token"]


def ask(lan, path, body, *, headers=None, fake=None, with_password=False):
    fake = fake or FakeCanceller()

    async def go(http, url):
        token = await _token(http, url)
        sent = headers if headers is not None else {"Origin": url, TOKEN_HEADER: token}
        reply = await http.post(f"{url}{path}", json=body, headers=sent)
        return reply.status, (await reply.json() if reply.status == 200 else await reply.text())

    status, answer = lan(go, fake, with_password=with_password)
    return status, answer, fake.asked


def test_a_job_is_paused_from_the_page(lan, run_job):
    job_id, _ = run_job()
    status, answer, asked = ask(lan, f"/api/jobs/{job_id}/control", {"action": "pause"})
    assert status == 200 and answer["paused"] is True and answer["action"] == "pause"
    assert asked == [(job_id, "pause")]


def test_a_machine_is_paused_as_a_drain(lan):
    status, answer, asked = ask(lan, "/api/machines/build-1/control", {"action": "pause"})
    assert status == 200 and answer == {"machine": "build-1", "action": "pause", "running": []}
    assert asked == [("build-1", "drain")]


def test_unknown_actions_and_other_pages_are_refused(lan, run_job):
    job_id, _ = run_job()
    assert ask(lan, f"/api/jobs/{job_id}/control", {"action": "explode"})[0] == 400
    assert ask(lan, "/api/machines/build-1/control", {"action": "remove"})[0] == 400
    status, _, asked = ask(lan, f"/api/jobs/{job_id}/control", {"action": "pause"},
                           headers={"Origin": "http://evil.example"})
    assert status == 403 and asked == []


def test_the_coordinators_refusal_is_its_own_words(lan, run_job):
    job_id, _ = run_job()
    fake = FakeCanceller(CoordinatorError("job x is finished; there is nothing to pause",
                                          "conflict"))
    status, text, _ = ask(lan, f"/api/jobs/{job_id}/control", {"action": "pause"}, fake=fake)
    assert status == 409 and "nothing to pause" in text
