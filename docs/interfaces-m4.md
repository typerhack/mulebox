# Interfaces for M4 (Docker Compose projects)

Contract added on top of [interfaces-m1.md](interfaces-m1.md). Design: [design.md](design.md).

## Needs nobody offers

`coordinator/needs.py`. Before 0.16.0 a job whose `needs` no worker offered waited in the
queue without a word, for as long as its client lived.

- `submit` replies `error` with code `no_worker` when workers are known and none offers the
  job's `needs`, offline ones included. The message names each machine and what it offers,
  and says what to change. The client exits 4. A repeated `idempotency_key` still returns
  its job. Before any worker has been seen nothing is refused.
- A queued agent job that cannot start now carries `waiting_for` (text) in `status_ok`,
  `queue_ok` entries and the `watch` stream, which re-sends when it changes. Reasons: no
  worker connected yet, every capable worker offline, or no worker offers the needs any
  more. Reservations never carry it: they are pinned to their machine. Both fields are
  additive, so the protocol version stays 1.
- `mulebox check` prints `queued, position 1; waiting: <reason>`; `mulebox queue` prints the
  reason on a line under the job. `workers.OFFLINE_AFTER_S` is the one definition of
  offline, shared with the dashboard's machines panel.
