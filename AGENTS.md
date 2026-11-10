# mulebox: rules for agents

mulebox is meant to become open-source software used by other people. Treat every change as
product work, not a personal script.

## Hard rules

1. **No emojis.** Not in code, docs, commits, comments, or chat replies.
2. **Versioning.** The version lives in [VERSION](VERSION) only (other places read it).
   Format `MAJOR.MINOR.PATCH`, starting at 0.1.0:
   - `PATCH` (0.1.0 -> 0.1.1): small fixes, docs, refactors without behaviour change.
   - `MINOR` (0.1.1 -> 0.2.0): new features or significant changes; resets PATCH.
   - `MAJOR` (0.x -> 1.0.0): **only on a release the user declares.** Never bump it on your own.
   Every change bumps the version exactly once, in the same commit.
3. **Project log.** Every change gets an entry in [PROJECT_LOG.md](PROJECT_LOG.md) (newest
   first, format at the top of that file) in the same commit as the change and the bump.
   No change without a log entry.
4. **Modular and reusable, strictly.** Small modules with one job each, imported where
   needed. Before writing code, find the existing module that does it and reuse or extend
   it; never duplicate logic. Shared pieces (SSH, config, protocol, logging, path safety,
   redaction) live in one module each under `mulebox/common/`.
5. **File size.** Aim for at most ~300 lines per code file; 500 lines is never accepted.
   Past 300, split by responsibility first. Applies to code and scripts, not docs.
6. **No personal data, ever.** This repo will be public and git history is forever. Never
   commit real IP addresses, hostnames, usernames, home paths, repository names of the
   author's projects, tokens, passwords, or keys. Use examples (`192.168.1.50`, `alice`,
   `build-1`, `/home/alice`, `example-app`). Machine-specific notes belong in the user's
   private ops repo, not here.
7. **Safety on build machines.** mulebox only writes and deletes inside its own configured
   roots, through the path-safety module. No disk tools, no system-path changes from jobs.
   Never test a destructive filter against a real machine.
8. **Track work in [docs/phases.md](docs/phases.md).** When asked "what is open?", answer
   from it and continue the next open task. Mark a task done only after its "done when"
   check passed.
9. **Docs follow code.** A behaviour change updates the relevant doc in the same commit.
10. **One design system.** Every screen follows [docs/design-system.md](docs/design-system.md):
    colors, type, space, corners and motion come only from its
    [tokens.css](docs/design-system/tokens.css), never typed into a component. A change to the
    system is made there first, with the user's agreement.

## Commits

- One logical change per commit; the subject starts with the new version, e.g.
  `0.1.1: fix queue position after cancel`.
- Never commit `.secret/`, `.env*`, keys, or local config with real hosts.
