# Module interfaces (M1.2 / M1.3)

The contract for the shared modules in `mulebox/common/`. Parallel work must match these
signatures; changes to this file go through the integrator. Design: [design.md](design.md).

General rules: Python 3.12+, standard library first, type hints, `@dataclass(frozen=True)`
for values, one exception module per concern (`class XError(MuleboxError)`), no I/O at
import time, no global state except loggers. Base exception in `mulebox/common/errors.py`:
`class MuleboxError(Exception)`.

## ids.py
- `new_id(prefix: str) -> str`: `"<prefix>-<26 char Crockford base32 ULID>"`, time-sortable,
  e.g. `job-01JC3X...`. Prefixes in use: `job`, `att` (attempt), `wrk` (worker), `sub`
  (client idempotency key), `req` (request).
- `is_valid_id(value: str, prefix: str | None = None) -> bool`
- `id_timestamp(value: str) -> datetime` (UTC)

## log.py
- `setup_logging(level: str = "INFO", *, json_lines: bool = False, file: Path | None = None) -> None`
  idempotent; text format `2026-11-03T12:00:00Z INFO mulebox.worker message`.
- `get_logger(name: str) -> logging.Logger` (names under `mulebox.`).

## config.py
- `ConfigError(MuleboxError)` with a message naming the file and the field.
- `ProjectConfig` (from `.mulebox.yml`): `project: str`, `needs: tuple[str, ...]`,
  `toolchain: dict[str, str]`, `setup: str | None`, `services: tuple[str, ...]`,
  `compose: tuple[str, ...]`, `jobs: dict[str, str]` (must contain `check`),
  `timeout_min: int` (default 30, 1..240), `exclude: tuple[str, ...]`,
  `env: dict[str, str]` (0.6.0; see interfaces-m3.md), `job_options: dict[str, JobOptions]`
  (config_jobs.py: `setup`, `compose`, `ports`; `for_job(project, name)` gives the project as that job
  sees it, and only the client reads it: a job's settings are what its `submit` carries, port names as
  `MULEBOX_HOST_PORTS` in `env`, which the worker removes before it checks names).
- `find_project_config(start: Path) -> Path` walks up to the filesystem root; ConfigError if none.
- `load_project_config(path: Path) -> ProjectConfig`
- `ClientConfig` (from `$MULEBOX_CONFIG` or `~/.config/mulebox/client.toml`):
  `coordinator: str` (ssh target, e.g. `build-1`), `remote_bin: str`
  (default `~/.mulebox/bin/mulebox`), `connect_timeout_s: int` (default 10).
- `NodeConfig` (on a node, `~/.config/mulebox/node.toml`): `name: str`,
  `roles: tuple[str, ...]` (`coordinator`, `worker`), `roots: Roots-compatible dict`
  (`jobs`, `cache`, `staging`, `runners`, all absolute), `slots: int` (default 1),
  `priority: str` (`preferred`, `normal` (default), `fallback`; slots from afar are 1..64, both in
  `common/node_settings.py` and editable from afar, docs/design.md, Node settings),
  `capabilities: tuple[str, ...]`, `coordinator: str | None` (ssh target; None if local),
  `dashboard: dict` (`mode`: `off|local|lan`, `port`: 8090, `lan_range`: private CIDR or
  None, `lan_address`: IPv4 inside `lan_range` or None, `lan_port`: same as `port`, `lan_tls`: false),
  `job_env: dict[str, str]` (environment for every job on this machine; `env:` of a project
  overrides it), `retention: dict` (`log_days`: 30, `step_days`: 365), `limits: dict`
  (`unattended_idle_min`: 15, `unattended_max_hours`: 24).
- `load_client_config(path: Path | None = None) -> ClientConfig`,
  `load_node_config(path: Path | None = None) -> NodeConfig`, `node_config_from(path, data)`
  (from parsed TOML, for a change checked before it is written, worker/node_file.py)
- YAML via PyYAML (`yaml.safe_load` only), TOML via `tomllib`. Unknown keys are errors.

## protocol.py
- `PROTOCOL_VERSION = 1`
- `class JobState(StrEnum)`: `uploading, queued, starting, running, cleaning, finished`
- `class Outcome(StrEnum)`: `passed, failed, cancelled, timed_out, interrupted`
- `ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]]`;
  `check_transition(old: JobState, new: JobState) -> None` raises `ProtocolError`.
  Any non-finished state may go to `cleaning` or `finished` (cancel/failure paths).
- `class MessageType(StrEnum)`: `submit, submit_ok, upload_done, status, status_ok, cancel,
  heartbeat, claim, claim_ok, claim_none, job_update, log_chunk, result, error`
- `@dataclass(frozen=True) class Message`: `type: MessageType`, `request_id: str`,
  `body: dict[str, Any]`, `v: int = PROTOCOL_VERSION`
- `encode(msg: Message) -> bytes` (one JSON object + `\n`, UTF-8, sorted keys),
  `decode(line: bytes | str) -> Message` (validates `v`, type, required body fields).
- `REQUIRED_FIELDS: dict[MessageType, frozenset[str]]`, e.g. submit needs `project, job,
  argv, idempotency_key, fingerprint, base_commit, client`; claim needs `worker,
  capabilities, free_slots`; heartbeat needs `job_id, lease`; log_chunk needs `job_id,
  offset, data`; result needs `job_id, outcome, exit_code, duration_s`.
- `ProtocolError(MuleboxError)`; unsupported `v` gives a clear upgrade message.

## ssh.py
- `SSHUnavailable(MuleboxError)` (connection failed, ssh exit 255),
  `RemoteError(MuleboxError)` (remote command failed; carries `exit_code`, `stderr`).
- `ssh_base_argv(target: str, connect_timeout_s: int = 10) -> list[str]`:
  `ssh -T -o BatchMode=yes -o ConnectTimeout=<n> -o ServerAliveInterval=10
  -o ServerAliveCountMax=3 <target>`: a node that vanishes fails the call in about 30 s, so the
  reconnect starts (ControlMaster is left to the user's ssh config). In a launchd service on a Mac, the argv
  starts with `python -m mulebox.common.disclaim`, which starts `ssh` as its own responsible
  process, so macOS lets it reach the local network (install.md, A Mac as a node).
- `run_remote(target: str, argv: Sequence[str], *, stdin: bytes | None = None,
  timeout_s: float | None = None, connect_timeout_s: int = 10) -> RemoteResult`
  where `RemoteResult(exit_code: int, stdout: bytes, stderr: bytes)`. The remote command is
  `shlex.join(argv)`: never a string built from user input.
- `stream_remote(target, argv, *, stdin: bytes | None = None, connect_timeout_s=10)
  -> Iterator[bytes]` yielding stdout lines; raises after the process ends non-zero.
- Tests never contact a real host: they patch `subprocess`.

## redact.py
- `class Redactor`: `__init__(secrets: Iterable[str] = (), patterns: bool = True)`,
  `add_secret(value: str) -> None` (ignores values under 6 chars), `redact(text: str) -> str`.
- Built-in patterns: GitHub tokens (`ghp_`, `gho_`, `ghs_`, `github_pat_`), AWS access keys,
  `Authorization: Bearer ...`, `password=` / `token=` / `secret=` style assignments, URLs
  with `user:password@`, PEM private key blocks. Replacement text `[redacted]`.
- `class StreamRedactor`: same, but `feed(chunk: str) -> str` and `flush() -> str`; holds
  back enough tail to catch a secret split across chunks.

## safepath.py  (M1.3)
- `PathOutsideRoots(MuleboxError)`, `UnsafePath(MuleboxError)`.
- `@dataclass(frozen=True) class Roots`: `paths: tuple[Path, ...]` (absolute, resolved at
  construction; must exist). `Roots.from_config(roots: dict[str, str]) -> Roots`.
- `resolve_inside(path: Path, roots: Roots) -> Path`: absolute paths only; resolves
  symlinks; must be strictly inside one root (never the root itself).
- `remove_tree(path: Path, roots: Roots) -> None`: validates, refuses mount points and
  trees containing mount points, then deletes with directory-descriptor-anchored operations
  (`os.open(..., O_DIRECTORY | O_NOFOLLOW)`, `dir_fd=`), never following symlinks, never
  crossing devices. A symlink target is removed as a link only. Missing path: no-op.
- `ensure_dir(path: Path, roots: Roots) -> Path`: create inside a root, mode 0o750.
- Linux mount detection via `/proc/self/mountinfo`; on macOS fall back to `st_dev` checks.

## Decisions made in M1.2 (0.3.0)
- ids: no monotonic ordering inside one millisecond (no module state); prefix is
  lowercase letters/digits; bad input raises `ValueError`. Extra: `new_ulid()`.
- log: configures only the `mulebox` logger (no propagation to root); each call replaces
  the previous handler.
- config: generic reading and `ConfigError(path, field, problem)` live in
  `config_reader.py` (re-exported from `config.py`). Toolchain versions must be quoted
  strings. `lan` mode needs `lan_range` and `lan_address`. Explicit path beats `$MULEBOX_CONFIG`. Extra:
  `client_config_path()`, `node_config_path()`. Duplicate YAML keys are not detected.
- protocol: envelope is exactly `v, type, request_id, body`; extra body fields pass
  through; `state`/`outcome` values are validated anywhere; `v` is checked before `type`.
  No self-transitions. Body fields beyond the contract: submit_ok `job_id, state`;
  upload_done `job_id, fingerprint`; status/cancel `job_id`; status_ok `job_id, state`;
  claim_ok `job_id, attempt_id, project, argv, fingerprint, base_commit, timeout_min`;
  claim_none none; job_update `job_id, state`; error `code, message`. `decode` has no size
  limit: readers must cap line length. Replies reuse the request's `request_id`.
- ssh: base `SSHError`; `RemoteTimeout` for local timeouts; `run_remote(..., check=True)`
  (False returns the result instead of raising); the command is
  `ssh_base_argv(...) + ["--", shlex.join(argv)]`. `RemoteError.stderr` is raw: redact
  before showing or storing.
- redact: also covers `ghu_`/`ghr_`, `ASIA` keys, `Authorization: Basic/Token`,
  `api_key=`, JSON `"password": "..."`; leans to over-redaction. StreamRedactor releases
  complete lines, holds back (longest secret - 1), holds PEM blocks up to 32 KiB.

## Decisions made in M1.3 (0.4.0)
- Split: `roots.py` (errors, `Roots`, `resolve_inside`), `mounts.py` (mount detection),
  `safepath.py` (public API; re-exports everything). Import from `safepath`.
- `RemovalDenied(UnsafePath)` for permission failures, so callers decide on escalation by
  type. `PathOutsideRoots` only for paths outside every root; everything else `UnsafePath`.
- Roots: overlapping/nested roots rejected; a root may not be or contain `/`, home or
  system folders, nor sit in `/dev`, `/proc`, `/sys`. Device and inode recorded and
  rechecked on every operation.
- `remove_tree` resolves symlinks in the parent path, never the final entry; may add u+rwx
  to read-only directories we own inside the tree (never the root or the target's parent).
- `ensure_dir`: path spelled under `Roots.paths`, no `..`, no symlink below the root.
- Linux: an unreadable mount table fails closed.

## download_lines.py and download_watch.py (1.15.0)
- `download_lines.parse(line) -> Seen | None`: one output line as `Seen(kind, what, name, done,
  total)`, `kind` `start|progress|end`, `what` `cache|tool|package|browser`; the shapes are in the
  module docstring. `size_bytes(number, unit)` (also used by worker/pullnoise.py).
- `DownloadWatch(live=True)`: `step(name)`, `line(text, at)`, `image_bytes(done, total, at)`,
  `reading(now, cpu_pct=None, net_bytes_s=None, net_scope=None) -> dict | None`. `live=False`
  for a GitHub runner's pages, which trail. `clean(value)` keeps a reading's known keys and
  types, for anything read off the wire.
- The reading, `activity.download` in a heartbeat and a `status` reply, and `doing.download` on
  a dashboard card (null when nothing downloads):

      {"what": "cache", "name": "pip cache", "step": "Run actions/setup-python@6d4fd22",
       "done_bytes": 1418315, "total_bytes": 9806923, "rate_bytes_s": 11819.3, "as_of_s": 30.0,
       "net_bytes_s": 614400.0, "net_scope": "job", "waiting_on_network": true,
       "quiet_s": 0.0, "stalled": false}

  `what` is also `image`, or `network` for an isolated runner's own traffic at an idle CPU with
  no line to name it. `done_bytes`, `total_bytes`, `rate_bytes_s` and `as_of_s` come from the
  printed figures, null when there are none; `net_bytes_s` is measured now, `net_scope` `job`
  (its own network) or `machine` (the node's, never judged); `quiet_s` and `stalled` (60 s
  with no byte) are null when nothing tells.
