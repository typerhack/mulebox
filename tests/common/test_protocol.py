import json

import pytest

from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import (
    ALLOWED_TRANSITIONS,
    PROTOCOL_VERSION,
    REQUIRED_FIELDS,
    JobState,
    Message,
    MessageType,
    Outcome,
    ProtocolError,
    check_transition,
    decode,
    encode,
)

S = JobState

SAMPLE_VALUES = {
    "steps": [],
    "hosts": [],
    "project": "example-app",
    "projects": [],
    "version": "1.2.3",
    "workers": [],
    "job": "check",
    "argv": ["pnpm", "check"],
    "idempotency_key": "sub-01JC3X0000000000000000000",
    "fingerprint": "sha256:abc",
    "base_commit": "0123456789abcdef",
    "client": "alice-laptop",
    "job_id": "job-01JC3X0000000000000000000",
    "attempt_id": "att-01JC3X0000000000000000000",
    "state": "queued",
    "lease": "client",
    "worker": "build-1",
    "capabilities": ["docker", "node"],
    "free_slots": 1,
    "timeout_min": 30,
    "offset": 0,
    "data": "line one\nline two\n",
    "outcome": "passed",
    "exit_code": 0,
    "duration_s": 12.5,
    "code": "not_found",
    "message": "no such job",
    "jobs": [{"job_id": "job-01JC3X0000000000000000000", "state": "queued"}],
    "repository": "example-org/example-app",
    "run_id": "123456789", "run_attempt": "1", "runner": "build-1-example-app",
}


def full_body(mtype: MessageType) -> dict:
    return {name: SAMPLE_VALUES[name] for name in REQUIRED_FIELDS[mtype]}


def envelope(**overrides) -> str:
    data = {"v": PROTOCOL_VERSION, "type": "status", "request_id": "req-1",
            "body": {"job_id": "job-1"}}
    data.update(overrides)
    return json.dumps(data)


# --- state machine -------------------------------------------------------------------

EXPECTED_ALLOWED = {
    S.UPLOADING: {S.QUEUED, S.CLEANING, S.FINISHED},
    S.QUEUED: {S.STARTING, S.CLEANING, S.FINISHED},
    S.STARTING: {S.RUNNING, S.CLEANING, S.FINISHED},
    S.RUNNING: {S.CLEANING, S.FINISHED},
    S.CLEANING: {S.FINISHED},
    S.FINISHED: set(),
}
ALL_PAIRS = [(a, b) for a in JobState for b in JobState]


def test_enum_values_match_contract():
    assert PROTOCOL_VERSION == 1
    assert [s.value for s in JobState] == [
        "uploading", "queued", "starting", "running", "cleaning", "finished"]
    assert [o.value for o in Outcome] == [
        "passed", "failed", "cancelled", "timed_out", "interrupted"]
    assert {t.value for t in MessageType} == {
        "job_ok",
        "submit", "submit_ok", "upload_done", "status", "status_ok", "cancel", "heartbeat",
        "claim", "claim_ok", "claim_none", "job_update", "log_chunk", "result", "steps", "error",
        "queue", "queue_ok", "projects", "projects_ok", "machines", "machines_ok", "logs", "watch",
        "reach", "reach_ok", "reserve", "acquire", "release", "runner_jobs"}


def test_transition_table_is_exact():
    assert set(ALLOWED_TRANSITIONS) == set(JobState)
    assert {k: set(v) for k, v in ALLOWED_TRANSITIONS.items()} == EXPECTED_ALLOWED
    assert all(isinstance(v, frozenset) for v in ALLOWED_TRANSITIONS.values())


@pytest.mark.parametrize("old,new", [p for p in ALL_PAIRS if p[1] in EXPECTED_ALLOWED[p[0]]])
def test_every_allowed_pair(old, new):
    check_transition(old, new)


@pytest.mark.parametrize("old,new", [p for p in ALL_PAIRS if p[1] not in EXPECTED_ALLOWED[p[0]]])
def test_every_forbidden_pair(old, new):
    with pytest.raises(ProtocolError):
        check_transition(old, new)


@pytest.mark.parametrize("old,new", [
    (S.UPLOADING, S.RUNNING), (S.QUEUED, S.RUNNING), (S.RUNNING, S.QUEUED),
    (S.CLEANING, S.RUNNING), (S.STARTING, S.UPLOADING), (S.QUEUED, S.QUEUED),
])
def test_forbidden_message_names_states(old, new):
    with pytest.raises(ProtocolError, match=f"{old} -> {new}"):
        check_transition(old, new)


@pytest.mark.parametrize("new", list(JobState))
def test_finished_is_terminal(new):
    with pytest.raises(ProtocolError, match="finished"):
        check_transition(S.FINISHED, new)


def test_transition_rejects_plain_strings():
    with pytest.raises(ProtocolError, match="JobState"):
        check_transition("queued", S.STARTING)
    with pytest.raises(ProtocolError, match="JobState"):
        check_transition(S.QUEUED, "bogus")


def test_protocol_error_is_mulebox_error():
    assert issubclass(ProtocolError, MuleboxError)


# --- required fields ------------------------------------------------------------------

def test_required_fields_cover_every_type():
    assert set(REQUIRED_FIELDS) == set(MessageType)
    assert all(isinstance(v, frozenset) for v in REQUIRED_FIELDS.values())


def test_required_fields_from_contract():
    assert REQUIRED_FIELDS[MessageType.SUBMIT] == {
        "project", "job", "argv", "idempotency_key", "fingerprint", "base_commit", "client"}
    assert REQUIRED_FIELDS[MessageType.CLAIM] == {"worker", "capabilities", "free_slots"}
    assert REQUIRED_FIELDS[MessageType.HEARTBEAT] == {"job_id", "lease"}
    assert REQUIRED_FIELDS[MessageType.LOG_CHUNK] == {"job_id", "offset", "data"}
    assert REQUIRED_FIELDS[MessageType.RESULT] == {
        "job_id", "outcome", "exit_code", "duration_s"}


# --- encode / decode ------------------------------------------------------------------

@pytest.mark.parametrize("mtype", list(MessageType))
def test_round_trip_every_type(mtype):
    msg = Message(type=mtype, request_id="req-42", body=full_body(mtype))
    assert decode(encode(msg)) == msg
    assert decode(encode(msg).decode("utf-8")) == msg


@pytest.mark.parametrize("mtype,name", [(t, n) for t in MessageType for n in sorted(REQUIRED_FIELDS[t])])
def test_decode_rejects_each_missing_required_field(mtype, name):
    body = full_body(mtype)
    del body[name]
    line = json.dumps({"v": 1, "type": mtype.value, "request_id": "r", "body": body})
    with pytest.raises(ProtocolError, match=f"missing required body field.*{name}"):
        decode(line)


def test_encode_format_is_one_compact_sorted_line():
    msg = Message(MessageType.LOG_CHUNK, "req-1",
                  {"offset": 5, "job_id": "job-1", "data": "a\nb\r\n c"})
    data = encode(msg)
    assert data.endswith(b"\n") and data.count(b"\n") == 1
    assert b"\r" not in data and b" " not in data
    assert data == (b'{"body":{"data":"a\\nb\\r\\n\xe2\x80\xa8c","job_id":"job-1","offset":5},'
                    b'"request_id":"req-1","type":"log_chunk","v":1}\n')
    assert decode(data).body["data"] == "a\nb\r\n c"


def test_encode_is_utf8_not_ascii_escaped():
    msg = Message(MessageType.ERROR, "req-1", {"code": "x", "message": "Grüße, 日本"})
    data = encode(msg)
    assert "Grüße, 日本".encode("utf-8") in data
    assert decode(data) == msg


def test_optional_body_fields_pass_through():
    body = {"job_id": "job-1", "state": "finished", "outcome": "failed", "position": 3}
    msg = decode(encode(Message(MessageType.STATUS_OK, "r", body)))
    assert msg.body == body


def test_message_accepts_type_as_string_and_defaults():
    msg = Message("claim_none", "req-1")
    assert msg.type is MessageType.CLAIM_NONE and msg.body == {} and msg.v == 1


def test_decode_accepts_crlf_terminator():
    assert decode(envelope() + "\r\n").type is MessageType.STATUS


@pytest.mark.parametrize("line,match", [
    (b"", "empty"),
    ("   \n", "empty"),
    ("{not json", "not valid JSON"),
    ('{"v": 1}{"v": 1}', "not valid JSON"),
    (b"\xff\xfe", "not valid UTF-8"),
    ("[1, 2]", "JSON object, got list"),
    ('"text"', "JSON object, got str"),
    ("null", "JSON object, got NoneType"),
    ('{"v": 1,\n"type": "status"}', "single line"),
    ("[" * 100000, "not valid JSON"),
    (123, "bytes or str"),
])
def test_decode_rejects_bad_json(line, match):
    with pytest.raises(ProtocolError, match=match):
        decode(line)


@pytest.mark.parametrize("field", ["v", "type", "request_id", "body"])
def test_decode_rejects_missing_envelope_field(field):
    data = json.loads(envelope())
    del data[field]
    with pytest.raises(ProtocolError, match=f"missing envelope field.*{field}"):
        decode(json.dumps(data))


def test_decode_rejects_unknown_envelope_field():
    with pytest.raises(ProtocolError, match="unknown envelope field.*extra"):
        decode(envelope(extra=1))


@pytest.mark.parametrize("overrides,match", [
    ({"v": "1"}, "'v' must be an integer"),
    ({"v": True}, "'v' must be an integer"),
    ({"v": 1.0}, "'v' must be an integer"),
    ({"type": 5}, "'type' must be a string"),
    ({"request_id": ""}, "'request_id' must be a non-empty string"),
    ({"request_id": 7}, "'request_id' must be a non-empty string"),
    ({"request_id": None}, "'request_id' must be a non-empty string"),
    ({"body": []}, "'body' must be an object"),
    ({"body": "x"}, "'body' must be an object"),
])
def test_decode_rejects_wrong_typed_envelope(overrides, match):
    with pytest.raises(ProtocolError, match=match):
        decode(envelope(**overrides))


def test_decode_rejects_unknown_type():
    with pytest.raises(ProtocolError, match="unknown message type 'launch'"):
        decode(envelope(type="launch"))


@pytest.mark.parametrize("v,side", [(2, "this side"), (0, "the other side")])
def test_decode_rejects_other_version_with_upgrade_hint(v, side):
    with pytest.raises(ProtocolError, match=f"v={v}.*v=1.*upgrade mulebox on {side}"):
        decode(envelope(v=v))


def test_version_checked_before_type():
    # A newer peer may use a type this side does not know; the hint must be about versions.
    with pytest.raises(ProtocolError, match="upgrade mulebox"):
        decode(envelope(v=2, type="something_new"))


@pytest.mark.parametrize("mtype,name,value", [
    (MessageType.JOB_UPDATE, "state", "exploded"),
    (MessageType.STATUS_OK, "state", 3),
    (MessageType.RESULT, "outcome", "success"),
    (MessageType.STATUS_OK, "outcome", "unknown"),
])
def test_decode_rejects_bad_enum_values(mtype, name, value):
    body = full_body(mtype) | {name: value}
    with pytest.raises(ProtocolError, match=f"'{name}' must be one of"):
        decode(json.dumps({"v": 1, "type": mtype.value, "request_id": "r", "body": body}))


def test_message_constructor_validates():
    with pytest.raises(ProtocolError, match="missing required body field"):
        Message(MessageType.CANCEL, "req-1", {})
    with pytest.raises(ProtocolError, match="unknown message type"):
        Message("nope", "req-1")
    with pytest.raises(ProtocolError, match="upgrade mulebox"):
        Message(MessageType.CLAIM_NONE, "req-1", v=2)


def test_encode_revalidates_mutated_body():
    msg = Message(MessageType.CANCEL, "req-1", {"job_id": "job-1"})
    msg.body.clear()
    with pytest.raises(ProtocolError, match="missing required body field.*job_id"):
        encode(msg)


@pytest.mark.parametrize("value", [object(), float("nan"), "\ud800", {1, 2}])
def test_encode_rejects_unserializable_body(value):
    msg = Message(MessageType.CANCEL, "req-1", {"job_id": "job-1", "extra": value})
    with pytest.raises(ProtocolError, match="cannot encode cancel message"):
        encode(msg)


def test_message_is_frozen():
    msg = Message(MessageType.CLAIM_NONE, "req-1")
    with pytest.raises(AttributeError):
        msg.request_id = "other"
