"""`mulebox feedback guide`: how an agent reports a problem with mulebox itself.

It lives here, beside the tool it explains, so it never falls behind `feedback draft`; the skill
only says when to read it (client/skill/SKILL.md). Plain text, no project names: it is printed on
anybody's machine.
"""

TEXT = """\
Reporting a problem with mulebox

When
  Only when mulebox itself did something wrong: a wrong result, a job that could not start
  with no clear reason, a refusal the contract does not explain, a crash, a confusing or
  wrong message, or a missing feature that cost real time. A check that failed because of
  the code is not a report: fix the code. Tell the user first, and make a draft only if
  they want it reported.

1. Gather the evidence while it is fresh
  - Every job id involved, not just one: the job that went wrong, the reruns, the job it
    compares with. A job id says nothing about anybody; the people who run mulebox look
    jobs up by it.
  - The exact command, its exit code, and what mulebox printed. Some notices are printed
    by the client only and are not in any log: copy them now.
  - mulebox status <id> --json: kind, outcome, stages, the version that ran it.
  - The log lines that show the problem, with their line numbers: mulebox logs <id>.
    Not just the last lines; a CI log, for one, ends in git cleanup.
  - The part of .mulebox.yml that matters, mulebox doctor, and mulebox --version.
  - What you expected, what happened instead, and whether you saw it on the current
    version or only remember it from an older one.

2. Draft it, scrubbed
    mulebox feedback draft <id> [<id> ...] --summary "<what happened>" \\
        --title "<short title>" --grep "<pattern for the lines that matter>" -o draft.md
  --log adds each job's last lines (--log-lines N for more). The draft holds the job ids,
  results, stages and versions. Then edit draft.md: add the evidence above in an
  "Evidence" section, as short quotes and tables, not whole logs.

3. Take out what is private
  The scrub replaces names of the project, people and machines, private links, addresses,
  email addresses and home folders, and redacts secrets. It cannot recognise private code,
  customer or patient data, internal service names, business text, or values from the
  machine's job environment. Read the whole draft and replace those with role words
  ("the api service", "a feature branch", "a customer record"). Never paste secrets, keys,
  tokens or .env contents, even redacted. If unsure, leave it out and say what kind of
  thing was there.
  If `post` refuses a line, it names the line and the kind of thing it found. Decide
  whether it really is private; if it is, take it out. Never reword something private
  just to get it past the check.

4. Ask, then post
  Show the user the final file and post only once they approve:
    mulebox feedback post draft.md
  It needs feedback_repo in client.toml and the gh command signed in. It posts exactly the
  file it checked, and nothing if the check fails.
"""
