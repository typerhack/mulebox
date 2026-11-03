# Project log

Every change to this repository is logged here, newest first, in the same commit as the
change, together with the version bump it causes. Rules: [AGENTS.md](AGENTS.md) (Versioning).

Entry format:

    ## <version> - <YYYY-MM-DD> - <patch|minor|major>
    - what changed and why (one line each)

## 0.1.0 - 2026-11-03 - minor
- Project created from the design work in a private setup repo: README, design, roadmap
  (docs/phases.md), versioning and project-log rules, agent rules.
- Design reviewed by an external model (core queue, dashboard, multiple machines); the
  adopted changes are part of docs/design.md.
- Groundwork measured on a real setup (M4 Pro laptop vs a 2014 4-core i7 on Wi-Fi): the old
  machine ran two real CI suites 1.8x and 3.5x slower than the laptop, but 2-3x faster than
  GitHub-hosted runners, with the laptop left idle. Basis for "offload, then queue".
