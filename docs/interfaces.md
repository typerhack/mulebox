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
  `timeout_min: int` (default 30, 1..240), `exclude: tuple[str, ...]`.
- `find_project_config(start: Path) -> Path` walks up to the filesystem root; ConfigError if none.
- `load_project_config(path: Path) -> ProjectConfig`
- `ClientConfig` (from `$MULEBOX_CONFIG` or `~/.config/mulebox/client.toml`):
  `coordinator: str` (ssh target, e.g. `build-1`), `remote_bin: str`
  (default `~/.mulebox/bin/mulebox`), `connect_timeout_s: int` (default 10).
- `NodeConfig` (on a build machine, `~/.config/mulebox/node.toml`): `name: str`,
  `roles: tuple[str, ...]` (`coordinator`, `worker`), `roots: Roots-compatible dict`
  (`jobs`, `cache`, `staging`, `runners`, all absolute), `slots: int` (default 1),
  `capabilities: tuple[str, ...]`, `coordinator: str | None` (ssh target; None if local),
  `dashboard: dict` (`mode`: `off|local|lan`, `port`: 8090, `lan_range`: CIDR or None).
- `load_client_config(path: Path | None = None) -> ClientConfig`,
  `load_node_config(path: Path | None = None) -> NodeConfig`
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
  `ssh -T -o BatchMode=yes -o ConnectTimeout=<n> <target>` (ControlMaster is left to the
  user's ssh config).
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
