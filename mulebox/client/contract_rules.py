"""The rules `mulebox contract` gives (contract.py): plain sentences an agent follows."""

TIME_LIMITS = (
    "no job has a time limit: a job that is working finishes, however long it takes, whether "
    "anyone is there or not",
    "every timeout_min a running job asks if all is well: a check_in event with elapsed time, "
    "stage, seconds since the last output, the job's CPU, and the machine's CPU and network",
    "answer it: mulebox ok <job-id> if it is fine, mulebox cancel <job-id> if it is not",
    "a job is stopped only when it is stuck: its question has gone unanswered for one more "
    "timeout_min, and it has had no output, CPU or service traffic of its own for that long, "
    "or 15 minutes if that is shorter",
    "a job the machine cannot measure stops only after 24 hours with its question unanswered",
    "a queued job is never stopped, and a job goes on if its client goes away; Ctrl-C and "
    "mulebox cancel stop it",
    "a stopped job shows stopped: stuck and exits 76: it says nothing about the code",
    "a running job that has done nothing for stuck_after_min (2, a project may set more) looks "
    "stuck: a stuck event, a warning in check and wait, and a line in mulebox status, with its "
    "evidence; slow (only a slow download or a trickle of data moves) and waiting (its last line "
    "says it waits) go on by themselves; asking (its last line wants input it never gets) and "
    "stuck do not: read mulebox logs <job-id>, then cancel it or keep waiting, and never send "
    "the same job again while it runs; it is a hint and stops nothing",
    "mulebox status shows the activity and any waiting question at any time",
    "any mulebox command in the project prints waiting questions and the results of jobs that "
    "finished while you were away, on stderr; --json stays clean; mulebox contract does not, as "
    "it needs no network",
)
WAYS_TO_WAIT = (
    "follow: mulebox check, attached, or mulebox events --job <job-id> --json",
    "be pinged when it ends: mulebox check --detach, then mulebox wait <job-id> as a background "
    "command",
    "check later: mulebox check --detach, then mulebox status <job-id>; your next mulebox "
    "command in the project also tells you the result",
)
RULES = (
    "if mulebox is unreachable, stop and tell the user; never run heavy commands locally",
    "an error says its code and a fix line: do the fix, or tell the user when it is theirs, "
    "before running the command again",
    "if mulebox contract says the mulebox skill is out of date, or this contract's schema is "
    "higher than the one your skill says it was written for, run mulebox skill update and read "
    "the skill again",
    "a detached job keeps running without you: cancel it with mulebox cancel if you no longer "
    "want it",
    "a check-in is a question to you: look at the activity, then answer with mulebox ok or "
    "mulebox cancel",
    "mulebox check does not repeat itself: on the same files and settings it gives the earlier "
    "result of the last 24 hours, or joins the same job if it is running; a result from while "
    "you were away counts, so do not retest; --again forces a run. A failure from before a "
    "mulebox upgrade does not count and runs again",
    "a compose job that failed in install, setup or its command keeps its containers on the "
    "node for a while (its summary says how long and gives the command): after a fix, mulebox "
    "check --from-stage <stage> reruns it from that stage with no new images or services. A "
    "change to the compose files, a Dockerfile, a lockfile, setup or install runs it from the "
    "start, and it says why. Code a service copies in at build time is the old code in a rerun: "
    "use a plain mulebox check for it. The last word on a change is a plain mulebox check",
    "run mulebox doctor before a project's first job, and after changing toolchain, needs or "
    "compose files: it finds what a job would fail on, before anything is uploaded; it exits "
    "1 if a job would not run, and warnings alone exit 0",
    "a failed job ends with a short summary on stderr: read it first, and the full log only "
    "if it is not enough",
    "old logs expire on the node: mulebox logs says so, and mulebox status still has "
    "the result",
    "do not ssh into the node to change, install or delete things",
    "the coordinator and the workers must be upgraded together: if mulebox doctor reports "
    "different versions, tell the user",
    "put no real secrets, hosts or personal paths in .mulebox.yml or workflows",
    "a database a job shares with anything else must have ${MULEBOX_JOB_SLUG} in its name, and "
    "never use an existing database; a database in a compose service of the job itself is that "
    "job's alone, so its name is free",
    "waiting in the queue is normal; do not cancel and resubmit to speed it up; if the wait "
    "may be long, run the job detached",
    "do not cancel other people's jobs",
    "a pinned toolchain version installs itself the first time a job needs it, which can take "
    "minutes; if that fails the job exits 5 and lists the versions the machine has: switch to one "
    "only if it matches the project, otherwise tell the user why the install failed",
    "show the user a feedback draft and get their approval before mulebox feedback post",
)


TESTS = (
    "a pass must show its tests ran: mulebox reads the summary pytest, vitest, jest, Pest, "
    "PHPUnit, cargo, mocha, Playwright, XCTest, Swift Testing and go test -v print, and a pass "
    "with a runner that ran none, or fewer tests than the last pass on the branch (else the "
    "default branch), fails with exit 8",
    "when tests were removed on purpose: mulebox check --fewer-tests \"<why>\"; the reason is "
    "kept with the job, so say it plainly",
    "tests: false in .mulebox.yml (or on a job) turns it off, for a job that runs no tests; "
    "tests: required also fails a pass that shows no runner's summary at all",
    "the end line of every job says how many tests ran; mulebox run is held only to none ran",
)
