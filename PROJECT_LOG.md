# Project log

Every change to this repository is logged here, newest first, in the same commit as the
change, together with the version bump it causes. Rules: [AGENTS.md](AGENTS.md) (Versioning).

Entry format:

    ## <version> - <YYYY-MM-DD> - <patch|minor|major>
    - what changed and why (one line each)

## 1.17.18 - 2026-11-13 - patch
- A job on a Mac node inherited the worker's `MULEBOX_SERVICE=launchd` (1.17.17), so a `mulebox` or ssh started by the job would have been disclaimed too. Seen when mulebox's own gate ran on the first real Mac node: 3192 tests passed and the 3 of `tests/common/test_ssh.py` failed on the prefix. The executor (`worker/executor.py`, both on Linux and the Mac) now leaves the marker out of a job's environment, and the suite clears it for every test (`tests/conftest.py`), so it passes wherever it runs. Test in `tests/worker/test_executor.py`.

## 1.17.17 - 2026-11-13 - patch
- A Mac node's worker could not reach its coordinator on the local network: `ssh: connect to host ... port 22: No route to host`, while the same ssh from Terminal worked. macOS asks a person before a program reaches the local network, and for a launchd agent it asks about the agent's program, Homebrew's Python, without ever showing the question; turning on the "Python" entry in Privacy & Security, Local Network did not help. Seen on the first real Mac node (M21), with every Homebrew Python (3.13 to 3.15) refused from launchd and Apple's `nc` let through.
- `common/disclaim.py`: in a mulebox launchd service on a Mac (the plist now sets `MULEBOX_SERVICE=launchd`), `ssh` is started through `python -m mulebox.common.disclaim`, which spawns it with `responsibility_spawnattrs_setdisclaim`, as Terminal starts a shell, so Apple's `ssh` answers for itself and needs no permission. It keeps stdin, stdout and stderr, passes on SIGTERM, SIGINT and SIGHUP, and gives back the exit code (255 if it cannot start). Nothing changes on Linux or for a dev machine's own commands. On the real Mac the worker then came online through it. Tests in `tests/common/test_disclaim.py` (real spawns on macOS) and `tests/services/test_launchd.py`; docs/install.md and docs/interfaces.md.

## 1.17.16 - 2026-11-13 - patch
- A Mac node with Docker Desktop was set up as offering "plain jobs" and "no Docker": `mulebox node-offers` ran `docker` with the ssh login's `PATH`, which on a Mac lacks `/usr/local/bin`, where Docker Desktop puts it. It now runs with the `PATH` the services get (`services/manager.py`, `service_path()`, the launchd agents' search path on a Mac, the inherited one on Linux), so it finds what a job finds. Seen on the first real Mac node (M21): after the fix setup said "it offers: docker". Test in `tests/worker/test_offers.py`; docs/install.md, A Mac as a node.

## 1.17.15 - 2026-11-13 - patch
- README brought up to date with what came since 1.6.0 (the user's ask): a node's settings window and priority, live reload of node.toml, rules for the order of the line (Order panel, `mulebox queue rules`, `mulebox project priority`), fair turns, download meters, `github_status` commit statuses, isolated runners for public repositories (the Security section said private only), macOS nodes and Apple builds (marked as new and not yet run on a real Mac node), `mulebox service` and `mulebox machine config` in the command tables.
- New pictures from the stand-in data: `node-settings-dark.png`, `order-light.png`, `downloads-dark.png`; every other picture taken again on 1.17.14. `tools/screenshots.py` gains the three shots (a script click opens the window and the panel; the downloads shot scrolls to the Jobs box). No product code changed.

## 1.17.14 - 2026-11-13 - patch
- Roadmap M24.6 done: a real pull request (a throwaway draft of this repository) showed the commit statuses from real `mulebox check` runs with `github_status: true`, `mulebox/check` passed and `mulebox/broken` (a job `false`) failed (exit 1), both on the pushed commit, posted by the dev machine's `gh`. The PR was closed and its branch, CI run, worktree and node project tree removed. Docs only.

## 1.17.13 - 2026-11-13 - patch
- Order panel: every project under "Other projects" is always shown; the "Show N more" and "Show the latest 3" button is gone, with `OTHER_SHOWN`. The user, asked whether the rest should always be open: "yes". No project and no set level is out of sight, and the panel needs no state for it any more.
- `OrderLevels.tsx` loses the open and chosen state and the chevrons; the two toggle tests in `order.projects.test.tsx` become one: 18 other projects all listed, a level set among them shown, no button. The list's id went with the button's `aria-controls` (Sol's review). docs/design.md, Order of the line, says so.

## 1.17.12 - 2026-11-13 - patch
- The segmented choice is radio marks, everywhere it is used: a node's Priority in the settings window, the project, branch, workflow and GitHub levels of the Order panel, and the period of the Statistics table. The user of the deployed dashboard on 2026-11-13: "the pattern [of the choice] in the machine settings is looking pretty bad. I don't like it at all. Especially the underline border, it's pretty bad." Of the three options of 1.17.11 ([docs/design-system/segmented-options.html](docs/design-system/segmented-options.html)) the user picked C, radio marks.
- `web/src/ui/Segmented.tsx` and `.seg` in `web/src/styles/components.css`: no box and no line; a ring before each word, the chosen ring filled in `--accent` with a heavier word, so never colour alone. A part keeps its width when chosen (each word holds a hidden heavier copy of itself), which it did not before. Still a radio group with one tab stop, arrow keys, Home and End; keyboard focus is the page's own ring around the part, a different mark from the chosen one; hover shades the part and darkens its ring; off or read only, nothing is in the accent and the chosen ring is filled in `--text-3`; 44 px parts on touch or under 520 px; no transition under reduced motion.
- The token `--chosen-line` is retired (tokens.css, and `--shadow-chosen` in theme.css): nothing else used it, tabs have their own line. The mockup keeps a copy for its "before the pick" comparison.
- Order panel rows (`OrderLevels.tsx`, two class changes): a row's choice keeps to the right edge also when it wraps under a long name, so the rings of stacked rows stay in columns and none passes the edge at 390 px. Before, a wrapped choice went to the left and the list read ragged.
- Tests: `web/src/ui/Segmented.test.tsx` (the chosen ring is marked and no other, a part's word and classes are the same chosen or not, keys, off). No existing selector changed. docs/design-system.md, Components, has the control.
- Seen in headless Edge on `npm run dev` with the scenes `settings` (also with the controls off) and `order`, and on the Statistics page, at 1440 and 390 px in both themes: nothing sideways, no part past its panel, parts 44 px high at 390, each part exactly as wide after a change of the choice as before, no console errors but the dev server's missing favicon.

## 1.17.11 - 2026-11-13 - patch
- Mockup only, no product code: [docs/design-system/segmented-options.html](docs/design-system/segmented-options.html), three ways to show the chosen part of the segmented choice (`web/src/ui/Segmented.tsx`), for the user to pick from. The user of the deployed dashboard on 2026-11-13: "the pattern [of the choice] in the machine settings is looking pretty bad. I don't like it at all. Especially the underline border, it's pretty bad." The window around it stays ("the new modal for each machine setting is pretty good, I like that").
- A, a tile in a track: a grey track with the chosen part as a tile edged in ink. B, ink fill: the outlined group with the chosen part filled in the text colour, its word reversed. C, radio marks: no box, a ring before each word, the chosen one filled in teal. None has an underline, none needs a new token; any of them retires `--chosen-line` from the segmented choice.
- Each is drawn in the control's three places (the Priority panel of the node settings window, three project rows of the Order panel, the Statistics period switch) at desktop size and in a 390 px frame with 44 px targets, with its rest, hover and keyboard focus states, a light and dark switch, and the control as it is today for comparison.
- Seen in headless Chrome at 1440 and 390 px in both themes: nothing past the edge, every part 44 px high and at least 44 px wide at 390, no console errors.

## 1.17.10 - 2026-11-13 - patch
- One rule everywhere, as the user confirmed ("one rule everywhere"): memory is shown in decimal GB too, RAM, swap and job memory alike, so a 16 GiB machine reads 17.2 GB. Nothing shown is 1024-based any more; what is left of 1024 converts inputs (`/proc`, `ps`, the `*_kib_s` fields) into bytes.
- The slot suggestion counted 6 x 2^30 bytes a job beside a decimal total; its budget is now 6 decimal GB (`node_settings.GB`), with the same text, "at about 4 cores and 6 GB a job". 8 cores and 16 GiB still give 2, 16 and 32 GiB still give 4 (tests). docs/design.md and the dashboard's test data say so.
- From Sol's review of 1.17.9: `format.test.ts` expected `bytes(999_600)` to read "1.0 MB"; it is 999.6 KB, and that test had been failing in 1.17.9. It now expects "999.6 KB", with 999_960 -> "1.0 MB" as the boundary case beside it.

## 1.17.9 - 2026-11-13 - patch
- Sizes and rates in decimal SI units everywhere a person reads them, the user's call of 2026-11-13: "Make everything consistent. Megabytes make more sense to me; MiB I don't have any sense of. Percent is perfect too." And: always one decimal, "906.4 MB", not "906 MB" ("that's two characters, why not show it").
- One rule each side: `mulebox/common/units.py` (`size`, `rate`, `rate_kib`) for the terminal and the logs, `bytes` and `rate` in `web/src/lib/format.ts` for the dashboard. B, KB, MB, GB, TB, 1000-based, whole bytes under 1 KB and one decimal above. The dashboard divided by 1024 but said MB, so pip's 906.4 MB wheel showed as 864 MB; it now reads 906.4 MB.
- Moved to it: `mulebox status` and check-in downloads and network (were KiB/MiB), `mulebox machine list` network (KiB/s), the snapshot and sending lines, the upload limit message (now "1.1 GB"), files taken back, the protocol line limit, the disk warning, cache and project sizes, the queue view's project sizes, the image-pull line in job logs, and the suggested slots' memory (a 32 GiB machine now reads 34.4 GB). `client/report.format_size` is gone.
- Kept as they are: API fields and their units (bytes, `*_kib_s`), node.toml settings, limits in code, and protocol errors that give an exact byte count. Percentages unchanged.
- docs/design-system.md, Type, states the rule; example output in docs/agents.md, interfaces-m2.md, interfaces-m4.md and troubleshooting.md follows it. Seen at 390 px in headless Chrome on the `downloads` scene and the machines page of `npm run dev`: the longer figures fit, nothing past the edge.

## 1.17.8 - 2026-11-13 - patch
- The Order panel's project levels, three faults Sol found in 1.17.7, each first shown by a failing component test (`order.projects.test.tsx`, `lib/order.test.ts`).
- A project that crossed the seven-day line on a reread, or whose job began or stopped waiting, moved between two separate lists, so its row was made anew and a focused choice lost the focus to the page. The two groups are now one list ("Project levels") with "Active in the last 7 days" and "Other projects" as headings inside it, and a row's key is its project alone: the row moves, stays the same row, and the focus stays on the same project and choice. The "Show N more" button now names that one list in `aria-controls`.
- A project called `constructor`, `toString` or `valueOf` met the properties every object has: its waiting count was a function, so it stayed among the others with the function's text as its note, and its level read as a function, a fourth choice with none chosen. Waiting counts are a Map, and every level is read through `levelOf` (`Object.hasOwn`), also for branches and workflows, in `changeOf`, `levelChoices` and `nameProblem` (which had called `constructor` "already in the list").
- A project whose first job waited after the rules were read had no row until the next read. The live line's project names are now among the rows, and the waiting job puts the project among the active.
- Docs: design.md (Order of the line).
- Not seen in a browser: the tests run in jsdom. Known and left: a focused row that moves into the closed part of a long rest goes with it.

## 1.17.7 - 2026-11-13 - patch
- The Order panel's project levels listed every project the node had ever seen in one flat list, about twenty of them old drills on the user's node. The user (2026-11-13): "I'd rather have all the projects here. Maybe a user wants to work on a project 2 years from now; he needs to have a record. But we say: these are used in the past 7 days, these are active. You still can use the others." So nothing is hidden or dropped: the list is split into "Active in the last 7 days" (a job or a GitHub run in that time, or one waiting now; by name, each with its fact, such as "12 runs, last 2 h ago" or "1 waiting, 6 runs") and "Other projects" (the latest run first, "last run 3 Oct", with the year once it is another one; a project with a level that never sent a job says "no run yet"). Every row is as settable as before, and a level shows wherever its project's use puts it.
- A rest of more than four shows its latest three and a button, "Show 15 more", that opens the others in place (`aria-expanded`, `aria-controls`, like the waiting list's); it starts open when a level is set among the hidden ones, and then stays as the viewer left it.
- API, backwards compatible: `queue_rules_ok` and `GET|POST /api/queue/rules` keep `projects` as the list of names and gain `project_activity: [{name, last_run, runs_7d}]` and `now` (`line_rules.project_activity`). One pass over the job history in place of the pass that listed the names, measured on a store of 20000 jobs of 25 projects: 7 ms against 5. No schema change. A page given no `project_activity` shows the one list it showed before.
- Tests: the query (a project last used 40 days ago, runs 8 and 6 days and 2 hours old, a job sent 9 days ago and started 3 days ago, a GitHub run, a project with a level and no job), the dashboard's API, and the panel (`order.projects.test.tsx`: the split and its order, a level given to an old project, the long rest closed and open, a waiting project as active, the answer without activity). The `order` scene of `npm run dev` has six active projects and eighteen others.
- Seen in headless Chrome on the `order` scene at 1440 and 390 px in both themes: the rest closed and, opened with Enter on its button, all eighteen rows; nothing past the edge, every control 44 px at 390, no console errors but the stand-in server's missing favicon.
- Docs: design.md (Order of the line), interfaces-m1.md and interfaces-m2.md.

## 1.17.6 - 2026-11-13 - patch
- A floating panel keeps the focus when its focused control turns disabled (`ui/Float.tsx`): after Save in the Order panel the focus dropped to the page, so Escape no longer closed it (seen on the deployed dashboard). Roadmap: M14.15 done, a project level set in the panel reordered a real line on the node with each row saying why.

## 1.17.5 - 2026-11-13 - patch
- Dashboard, two things the user said of the deployed page on 2026-11-13.
- The All machines table: "small tweak needed: the table row, everything too stuck at the sides". The first and the last cell of a row, header included, now keep 12 px (`--space-3`) from the row's edges, so the shaded row of the shown machine no longer has its name and its buttons on its border. In `.data-table`, so the Statistics breakdown has the same; History uses no table. Stacked cards under 1100 px are as before.
- The node settings window: "this UI kind of hurts my eyes", "maybe use the same panel style we have in this part of the UI" (the top row's Memory, Disk and Machines). The four-column table with its heavy header rules is gone. The window's body is the page's colour and holds the top row's own panels (`Panel`, `Fact`, `Offers`): Slots and Priority, each with its icon and name, one line on what it means, then Suggested, Yours and Runs with as rows with the name left and the value right, a hairline between rows and the reason under its row; beside them "Reported by the node" with version, state, cores and the offers as chips, as the Disk panel lists its facts. One column under 760 px of the window's own width. Every fact, control and state is kept: the stepper with "use the suggested" (now left of it, so the stepper does not move), the priority choice with its line, now, unsaved and pending with "Drop it" (44 px wide too under 520 px, it was 39), the strips, read only, an older node, All as suggested, Close or Cancel, Save changes, Escape and focus back.
- `Window` takes `ground` for a body that holds panels; the `.ledger` styles are replaced by one small grid, `.settings-grid`. Tests: the window's helpers find a setting by its panel (a region named Slots or Priority) where they looked for a table row; what they expect to read is unchanged. docs/design-system.md, Components, says both.
- Seen in headless Chrome on the `settings` scene of `npm run dev` at 1440 and 390 px in both themes, with two machines and with three and the controls off (as suggested, unsaved, pending with its error, an older node, read only), the window beside the top panels in one picture: nothing past the edge, every control 44 px at 390, Escape closes and the focus is back on the settings button, no console errors.
## 1.17.4 - 2026-11-13 - patch
- The Order panel, from Sol's review of 1.17.2, each with a component test (`order.live.test.tsx`, with answers given in a chosen order): an edit made while a save was on its way was lost, as only the footer was disabled and the answer replaced the whole copy; now nothing takes an edit until the save is back, and a save forgets only what it sent (`unsent`, now `web/src/lib/edits.ts`, shared with the node settings window).
- Reading the rules again over unsaved edits sent other viewers' changes back: edit, close, someone turns fair turns on, reopen, Save sent fair turns off. The edits are now a change to the rules they were made on, laid over every fresh read, so Save sends only what this viewer changed.
- Answers in any order: a read asked before a save and answered after it brought the old rules back and cleared "Saving". Every request takes a turn (`web/src/lib/turns.ts`, shared with the node settings window), a save takes one, an older answer is dropped, and the rules are read again after a save.
- The rules were read only on opening; an open panel now reads them every 5 s while the page is visible, keeping the viewer's edits.
- When the last waiting job of a lane started, the lane and the panel open under it went, with its focus and what was typed. One panel is now mounted where the lanes are (`OrderPanel`), hanging under the button it was opened from by CSS anchor positioning (`.pop-opener`), at the top right of the lanes where that button has gone or the browser cannot anchor; closing gives the focus to that button, else another Order button, else the lanes.
- Design system: the panel's sizes are tokens (`--pop-width`, `--pop-height` in tokens.css, within the user's agreement of 2026-11-13 on panels and windows), and the order rules' chosen parts use `--chosen-line`. One segmented choice and one stepper for the window, the panel and the Statistics page (`ui/Segmented.tsx` with `small`, `ui/Stepper.tsx` with `step`); the switch in `ui/Switch.tsx`; `ui/Controls.tsx` and `--shadow-mark` are gone.
- Seen with the `order` scene of `npm run dev` in Chrome at 1440 px (the panel 4 px under its button, right edges equal) and 390 px (in a 390 px frame, nothing past the edge), no console errors.

## 1.17.3 - 2026-11-13 - patch
- The line, fixes from Sol's review of 1.17.1, each first shown by a failing test: a move cleared the `priority` a row had from a move before pins existed, so a row others were pinned to lost its place (A, B, C, D at 4, 3, 2, 1, A down, then C first gave C, B, D, A, not C, B, A, D); a move now leaves `priority` alone, as the pin already sets the moved row's place.
- Moving two rows of one place back and forth halved the room between their `pin_order`s each time, and on the 52nd move the middle was one of the ends, so the line came out wrong. When there is no middle left, the rows of that place are numbered 0, 1, 2 again in the same write (`line_moves.OTHERS`, `line_moves.write`); a test moves two rows 200 times.
- `usual.lengths` read every passed run of the projects in line (1000 runs for one queued job) inside the claim's `BEGIN IMMEDIATE`. It now looks up each project, job, command and place in time once, in one query per kind passed as JSON, and each lookup stops at the 20 runs it counts; ten times the history now takes about the same work (a test counts SQLite's steps), and the query-count tests still hold.

## 1.17.2 - 2026-11-13 - patch
- Dashboard: the queue order settings (M14.15), option A of the mockup the user picked. An Order button on every waiting line's heading (and under the lanes when nothing waits) opens a panel anchored to it (`web/src/features/order/`, `ui/Float.tsx`): the rules as a ladder, strongest first, so which rule wins is on the page (by hand, levels added up, fair turns, shortest first, arrival; Sol's point), with the switches for fair turns and shortest first at their rank and aging with its minutes inside Levels; then a level per project, branch pattern and GitHub workflow and one for GitHub runs, High, Normal or Low, a level the CLI stored outside those shown as its number. Changes are a copy until Save ("Unsaved changes"), which posts only what differs; "Reset to defaults" asks twice; with the dashboard's controls off the panel opens read-only.
- Each waiting row says why it stands where it does, as a second line with the rule's icon ("ahead: project high; fair turn 1; usually 4m"), from `order`; the coordinator's full `place_reason` is its tooltip and on the job's page.
- Design system in code: a switch, the segmented choice as a radio group with arrow keys (the Statistics page's period choice uses it too) and a number stepper (`web/src/ui/Controls.tsx`).
- The stand-in API for `npm run dev` answers `/api/queue/rules` and has an `order` scene; `MULEBOX_MOCK_CONTROLS=off` (from the node settings window) also makes the rules read only.

## 1.17.1 - 2026-11-13 - patch
- The order of the line, as the user decided (design.md, Order of the line): a move by hand pins only the moved job (`front`, or just ahead of or behind another job's place, in new columns `pin_side`, `pin_job`, `pin_order`, coordinator/line_moves.py), so a later rule change still orders the rest; 1.17.0 wrote the whole visible order into every waiting job. A pinned job whose neighbour left the line keeps that place. GitHub slots, upgrades and `boost` move the same way.
- Shortest first counts a job with no past runs as the median of the known lengths in line (none known: arrival), not after every known job.
- A workflow level: the runner's job-started hook sends GITHUB_WORKFLOW with `reserve`, kept as `jobs.workflow` (schema 22, migration 21 -> 22), `workflows` in the rules, `mulebox queue rules --workflow NAME=LEVEL`, `/api/queue/rules`, and `place_reason`.
- A long line is read in a fixed number of queries: the usual lengths of every row at once (`usual.lengths`), one read of the line per request, shared with the waiting reasons, `upgrades.ahead_of` and a GitHub slot's grant. Found by Sol: 6000 waiting jobs with shortest first took 4.4 s inside the claim's transaction; now 0.2 s. A test bounds the queries.
- Aging is said in whole steps (`waited 30m or more +1`), and the dashboard redraws on a changed `place_reason` or `moved`, so it redraws when aging changes the order, not every minute.

## 1.17.0 - 2026-11-13 - minor
- Order rules for the line (M23.3, M24.4; design.md, Order of the line): a level per project (`mulebox project priority <project> low|normal|high|-3..3`) and per branch or pattern, a level for GitHub runs, aging (default every 30 min adds a level, so nothing waits for ever), fair turns between projects (counting what each already runs) and shortest first from `usual`, set with `mulebox queue rules` or `GET|POST /api/queue/rules` and kept in the coordinator's `meta`, never in `.mulebox.yml`, so a project cannot raise itself. Moves by hand still come first, arrival last. One order (`coordinator/line.py`) for claims, GitHub grants, upgrades, positions and moves, read in the claiming transaction. With the defaults the line is exactly the old one; while a rule is on, `status`, `queue` and the dashboard give each waiting job's `place_reason` and `order`. The dashboard's settings page is M14.15.

## 1.16.5 - 2026-11-13 - patch
- AGENTS.md hard rule 11 (the user's): every model loads the frontend-design skill before any UI step, the lead agent too when it merges or checks UI work, and every subagent prompt that touches UI says so.

## 1.16.4 - 2026-11-13 - patch
- Roadmap: M14.14 (node settings window) and M23.9 (config reload) done on the real node from the dashboard in real Edge: slots 2 to 3 reached node.toml with no restart, three jobs ran at once, and back to 2 showed pending until the node's next check-in. M23.4 (node priority) still needs a second node.

## 1.16.3 - 2026-11-13 - patch
- Node settings window, from Sol's review, each fault first shown by a component test (`NodeSettings.live.test.tsx`, with answers given in a chosen order):
- An edit made while a save was on its way was lost: the controls stayed usable, and the save's end emptied all edits. Now the stepper, the priority choice and "use the suggested" take nothing until the save is back, and a save forgets only the edits it sent (`unsent` in `web/src/lib/nodeSettings.ts`).
- Answers could overwrite each other out of order: a read asked before a save and answered after it brought the old values back, and a save's late answer brought "pending" back after a read had shown the change taken. Every request now takes a turn and an answer older than the newest turn is dropped; reads wait while a save is on its way, and after every save or drop the node is read once more.
- An open window went stale: it read again only when slots, priority or the pending mark of its row changed. It now also follows the row's state (offline, paused), jobs and version, and asks every 5 s while open and visible, as a failed write leaves the row's pending mark as it was and only the settings answer carries the error. A slow answer gets no second request on top; a failed read says so and the words go once one works; the viewer's edits are kept through every read.
- Design system: `--scrim`, `--window-width` and `--chosen-line` are tokens in `docs/design-system/tokens.css` (the user's agreement of 2026-11-13 to windows and panels in the system); theme.css only names them, where it had typed the 72%, the width and the line itself. Noted in design-system.md, Components.
- Seen in headless Edge on the `settings` scene of `npm run dev` at 390 and 1440 px, both themes: nothing past the edge, the window 800 px wide at most, the scrim and the accent line as before, no console errors; a save read "3 pending", then "3 now" by itself.

## 1.16.2 - 2026-11-13 - patch
- Dashboard: the node settings window (M14.14), the user's pick "Suggested and yours": a settings button on every machine's row (Machines box and Machines page) opens a centred window that is one table, each setting with what mulebox suggests and why, the viewer's value (slots as a stepper from 1 to 64, priority as Preferred, Normal or Fallback with one line on what the chosen level means) and what the node runs with, then what the node reports, locked (version, state, cores, what it offers). An edit reads "unsaved" until Save and "pending" only after Save, until the node took it; a pending setting can be dropped; a change the node could not write shows its reason; a taken suggestion is said to be a fixed value. A node on an older mulebox says "upgrade it first" and a dashboard with its controls off says so, both with nothing to change. A machine's row carries a small clock while a change waits. One card per setting when narrow, 44 px controls on touch and under 520 px.
- Design system parts in code: `web/src/ui/Window.tsx` (dialog semantics, Escape and a close button, focus in on open, kept inside and given back to the opener, the page under it inert), `Stepper.tsx` (typed values, out of range refused with the range said) and `Segmented.tsx` (a radio group moved by arrow keys); a scrim, a window width and the chosen part's accent line named once in theme.css from tokens.
- `npm run dev`: node settings in the stand-in API (`web/dev/settings.ts`) and a scene for them (`MULEBOX_MOCK_SCENE=settings`, `MULEBOX_MOCK_CONTROLS=off`). A scene no longer stops the dev server: the stand-in history could not be made from a scene's empty list of finished jobs.
- Not in the window, as no route gives them: a node's toolchains and roots. The mockup's "New jobs" switch is left to the Pause button beside the settings button.

## 1.16.1 - 2026-11-13 - patch
- node.toml written from afar (`worker/node_file.py`), from Sol's review: a file over 1 MiB is refused with the reason rather than read in part, as the write would have replaced it with its first MiB; a setting's trailing comment is kept (`slots = 2 # leave room` becomes `slots = 3 # leave room`); a quoted key (`"slots" = 2`, `'slots' = 2`) is taken for its setting, where before a second `slots` line was added and the change stayed pending with an error.
- design.md, Node settings: the slot suggestion, the level names with the 30 s wait, and slots and priority alone from afar marked as the user's decisions of 2026-11-13.

## 1.16.0 - 2026-11-13 - minor
- Node settings from afar (M23.9, M23.4; the user's ask for a settings window per node, M14.14): `mulebox machine config <name> [--slots N] [--priority preferred|normal|fallback] [--cancel] [--wait]`, the `node_settings` request and `GET|POST /api/machines/<name>/settings` show a node's slots and priority, what waits, and a suggestion from its cores and memory (about 4 cores and 6 GB a job), and change them. The truth stays in each node's node.toml: the coordinator holds the change (`workers.wanted`, schema 21), the worker gets it with its next claim or heartbeat reply, writes it into its own node.toml through safefile (a symlink refused, comments kept, checked with the service's own reader) and reports what it has (`settings` in claims and heartbeats), which clears it. Only slots and priority: capabilities and `[job_env]` stay hand edits, as a wrong one fails jobs and `[job_env]` reaches every job's processes. A worker older than this one is refused with "upgrade it first".
- Config reload (M23.9): the worker reads node.toml again within 2 s of a hand edit and takes `slots`, `priority` and `capabilities` from the next claim, with no restart; a lower count stops no running job, a file that does not read keeps the old values, other changed fields are logged as needing a restart.
- Node priority (M23.4): `priority` in node.toml (`normal` if left out); a node leaves a job to a free, online, unpaused node ranked above it that offers what the job needs, for 30 s at most. Shown in `mulebox machine list` and the dashboard's machine rows (`priority`, `settings_pending`).
- `common/config_node.py`: node.toml's `[dashboard]`, `slots` and `priority` reading, out of config.py to keep it under 300 lines; `node_config_from` reads a node config from parsed TOML.

## 1.15.4 - 2026-11-13 - patch
- Roadmap: the Down meter seen on the deployed dashboard in real Edge with a drill job's large pip download (M23.11); a real CI cache restore stays open.

## 1.15.3 - 2026-11-13 - patch
- The Down meter, fixes from Sol's review of 1.15.1: a GitHub run's figures now read "at least 12.0 of 41.0 MB" (and "at least 18.0 MB so far") on the card itself, not only in a hover title that touch screens never show. A size with nothing counted yet (pip's `Downloading torch (906 MB)`) drew a definite 0% meter and read "906 MB in all", as if finished; a share now needs both figures, so it is the open, dashed track with "906 MB to download". On a narrow card (390 px, a frozen and boosted GitHub run with its marks and menu) the amount squeezed the track away and spilled; the row now wraps, putting the amount on its own right-aligned line under the track (`.meter-wrap`, components.css). Seen in headless Chrome at 390 and 1440 px in both themes with the `downloads` scene, which gains a frozen, boosted run and a size-only download.

## 1.15.2 - 2026-11-13 - patch
- Download readings, fixes from Sol's review of 1.15.0: junk that looked like progress (`| | 10% of ... MiB`, a size of 400 nines) raised out of log processing; numbers are now bounded, a size must be finite, and `download_lines.parse` never raises. An isolated runner at 2 KiB/s read as stalled, as traffic under 4 KiB/s counted as none: any byte, in its traffic or its printed figures, now counts. Playwright's tenths (one line in 102 s for 1 GiB at 1 MiB/s) read as stalled between them: its lines alone now judge against twice the longest gap seen, and say nothing before the first. A named end (`..., done`, uv's `Downloaded torch`) cleared another package's reading; it now ends only its own. Image readings never ended: they end at their total, and when pullnoise.py sees every layer with its data, before a long extraction.
- Docs: design.md, Downloads.

## 1.15.1 - 2026-11-13 - patch
- The download meter on a running job's card (M23.11), option A of the three mockups, the user's pick: a "Down" meter under Cores on agent jobs and GitHub runs, shown only while `doing.download` is there. It fills when the total is known and is an open, dashed track when not, with "Downloading <what>" and the speed as two facts on a line below, which wrap at 390 px. Once the worker counts the download as stopped, the fill and a warning icon take the warning colour and the line reads "No bytes for 75 s", from `quiet_s`. The speed is the job's own measured traffic first, then what its tool printed; the node's traffic only when there is nothing else, and then named "whole node". A GitHub run's figures are announced as "at least", as its runner writes output in blocks. Not load, so it keeps one solid fill in the Rainbow style too. `web/src/lib/download.ts`, `web/src/features/jobs/DownloadMeter.tsx`, with tests; seen in headless Chrome at 390 and 1440 px in both themes and both meter styles against the stand-in API (`MULEBOX_MOCK_SCENE=downloads`).
- Fixed: `npm run dev` with any `MULEBOX_MOCK_SCENE` did not start, as a scene has no finished jobs for the stand-in history.

## 1.15.0 - 2026-11-13 - minor
- Download readings (the user's ask, M23.11): a running job says what it is downloading, how much of how much, how fast, and whether it waits on the network or stalled, so a cache restore at 0.6 MB/s over the node's VPN, at no CPU, does not look hung. `download` in a heartbeat's `activity` (`common/download_watch.py`), in `mulebox status`, check-ins and a card's `doing` on the dashboard, sent with the heartbeats that already go. Read from the lines tools print (`common/download_lines.py`): GitHub's cache restore, setup-python and setup-node tool downloads, pnpm, pip, uv, Playwright and image layers; a CI run's at the times its runner stamped them. An isolated runner's own traffic is measured (its container's network); elsewhere the node's is shown and never judged. A card's fingerprint follows it in 5% steps. The card's look is for later.

## 1.14.5 - 2026-11-13 - patch
- Mockups (docs/design-system/mockups-2026-11-13.html): node settings, download progress on a job card and queue order, three options each, drawn by a Fable subagent and reviewed by Sol. The user picked node settings C (suggested and yours), download progress A (a second meter) and queue order A (an Order button on the line).

## 1.14.4 - 2026-11-13 - patch
- Design system: a switch, a segmented choice, a number stepper, an anchored panel and a window, with `--shadow-2` now under every floating surface, not menus alone (the user's agreement), for the node settings and queue order screens.

## 1.14.3 - 2026-11-13 - patch
- CI: `SEGMENT_DOWNLOAD_TIMEOUT_MINS: 1` for the whole workflow (M23.11, first step): over the node's slow VPN link a GitHub cache restore in setup-python or setup-node stalled for actions/cache's default 10 minutes at 0% CPU; now it gives up on the cache in a minute and installs without it. A test keeps it. The node's traffic keeps the VPN (the user's call).

## 1.14.2 - 2026-11-13 - patch
- ssh calls send a keepalive every 10 s and give up after 3 unanswered (`common/ssh.py`): when the node went down mid-check, `mulebox check` sat silent for over 10 minutes waiting for the operating system to drop the connection; now the call fails in about 30 s and the client's "connection lost, reconnecting" shows. A quiet job is not affected, as the node's ssh answers the keepalive.

## 1.14.1 - 2026-11-12 - patch
- Roadmap: M23.11, CI package caches without the slow download: GitHub's cache restore over the node's VPN tunnel stalls and holds a setup step for actions/cache's 10-minute timeout; first a 1-minute timeout, then caches kept on the node per isolated place.

## 1.14.0 - 2026-11-12 - minor
- A pass on GitHub (M24.6, `client/github_status.py`): with `github_status: true` in `.mulebox.yml`, `mulebox check` posts its result to the commit it ran on as the status `mulebox/<job>` (success, failure, or error when the job gave no result), so a pull request shows it and it can be a required check. Only when the files are exactly a pushed commit (clean worktree, HEAD on a remote-tracking branch), settled before the job is sent; posted by the dev machine's own `gh`, so nothing reaches in to the node. Not with `--detach`. A commit status, as a check run needs a GitHub App.

## 1.13.10 - 2026-11-12 - patch
- Roadmap: M24 (Answers an agent can trust), from similar tools read with the user (macserve, gatehaul, remote-dev, crabbox, local-ci): proof that tests ran, rerun from the failed stage, files back, fair turns between projects, one job across slots, a pass on GitHub, a fix on every error. M23.5 gains a health check before jobs. Signed results, fixed Apple recipes, per-machine rules and patches back parked; a Stop hook dropped (the user's call).

## 1.13.9 - 2026-11-12 - patch
- Roadmap: M21.5 (CI on macOS) done: the `macos` job passed on GitHub's macOS machine on every run since 1.13.5.
- Roadmap: M23.6's open point closed: a worker restart on 1.13.8 during a real CI run took under a second, and both jobs in isolated runners were taken over and passed.

## 1.13.8 - 2026-11-12 - patch
- A worker restart with a CI job in an isolated runner took systemd's full 90 s and ended in a timeout (seen in the drill of 1.13.7 on the node): with `--sig-proxy=false` the `docker run` client ignores SIGTERM, so it held the worker's stop. The worker now kills its own client when it leaves a container to the next worker; that ends only the client, the container runs on (checked on the node) and Docker still removes it when it ends.

## 1.13.7 - 2026-11-12 - patch
- An isolated runner's container outlives a worker restart (M23.6, `runners/place_handover.py`): a deploy removed every place's container, also one whose one-job runner GitHub had just given a job, which then hung for about 10 minutes. On stop a container is now kept if its job has asked or GitHub refuses to delete its runner (it has given it a job); only one whose runner GitHub deleted is removed, so no job slips in between. It runs with `--sig-proxy=false`, so the worker's stop signal does not reach it, and the next worker follows it, answers its job if nothing has (same reservation key), and ends its round. Upgrades that wait for busy places were weighed and left out: GitHub can hand a runner a job between the check and the restart (design.md, Worker restarts).

## 1.13.6 - 2026-11-12 - patch
- docs/design-system.md names the copy button of 1.13.3 and 1.13.4: its icons (`copy`, then `check`), and the long line it sits beside, cut with an ellipsis, whole in its tooltip.

## 1.13.5 - 2026-11-12 - patch
- The macOS test fix of 1.13.3 covered one test of a stopped process group; a second, stopping a group with a child, failed the same way on GitHub's macOS machine. Every test that checks a stopped group is gone now gives its last process a few seconds to be reaped.
- Roadmap: M23.6 names an open issue seen while deploying 1.13.3 with CI starting: a worker restart removes isolated places' containers even when GitHub has just given their runner a job, which then hangs for about 10 minutes.

## 1.13.4 - 2026-11-12 - patch
- The copy button of 1.13.3 did nothing on the dashboard's LAN address: over plain HTTP the page is not a secure context and browsers give it no clipboard API (seen in Edge on the node). It now falls back to copying through a hidden text field.

## 1.13.3 - 2026-11-12 - patch
- Dashboard: a running job's card cut a long GitHub step name (such as `Run actions/setup-python@` and a 40-character commit) only past the card's edge, which also pushed its Cores meter out. The step now ends in an ellipsis inside the card, its whole name in the tooltip, with a small button beside it that copies the whole name (`web/src/ui/Copy.tsx`, reusable for any long line).
- A macOS test of stopping a group left by an earlier worker read the group as alive while its last process, reparented, was still a zombie waiting for launchd (seen once on GitHub's macOS machine). It now gives the group a few seconds to go.

## 1.13.2 - 2026-11-12 - patch
- The macOS node work (built in its own branch as 1.3.0 to 1.10.1) and the isolated runners (1.3.0 to 1.5.0) were merged into one line: the Mac commits were replayed after 1.5.0 as 1.6.0 to 1.13.1, each keeping its kind of bump, with the versions in their log entries, roadmap lines and docs renumbered to match. The conflicts were in runner management, where both sides changed the same code: the Mac side moved runner services behind `mulebox/services/`, the isolated side added runners with no service; both kept.
- A Mac test checked that a job runs at niceness 5, which holds only when the test process itself is not niced; under a parallel run another test had raised it, and the job read 10. It now checks five above its own.

## 1.13.1 - 2026-11-12 - patch
- From Sol's review of 1.13.0 (M22.4): with a Podfile and no workspace yet (a fresh checkout), init tests the workspace `pod install` makes, not the bare project; a workspace's listed projects (`contents.xcworkspacedata`) give their schemes and platforms; a project with no shared scheme beside a `Package.swift` falls back to `swift test`.
- A watchOS, tvOS or visionOS app is told to pin its simulator runtime, as a job without a pin gets an iOS one; the note on the scheme says the destination is worked out from every target. A React Native app's `ios/` or `macos/` beside a gate already found is named, not left out silently.
- docs/install.md: each Xcode's license, first launch and runtimes with its own `DEVELOPER_DIR`, as the commands otherwise use the selected one, which can be the Command Line Tools.
- Not changed: choosing the destination from the chosen scheme's own targets would need reading the scheme's build references; the note asks to check it instead.

## 1.13.0 - 2026-11-12 - minor
- `mulebox init` for Apple platforms (M22.4, `client/init_apple.py`): for an `.xcworkspace` or `.xcodeproj`, `xcodebuild test` of its shared scheme (the one named after it, else the first), in the job's own simulator when a target builds for iOS, watchOS, tvOS or visionOS (`SDKROOT`, or `SUPPORTED_PLATFORMS` of an `auto` target), else on the Mac, with the job's DerivedData, the Swift package cache and no signing; `pod install` and `cache-cocoapods` for a Podfile; `swift test` for a `Package.swift` alone. It pins the Xcode the dev machine selects. `Pods/` and `DerivedData/` are not parts of a project.
- docs/install.md: Apple builds on a Mac node, what a person prepares once (Xcode in `/Applications`, its license and first launch, simulator runtimes, CocoaPods).
- From Sol's review of 1.12.0 (M22.3): the CocoaPods cache is shared by a project's branches, and CocoaPods empties one another version wrote, so agents' docs say to keep one CocoaPods version per project. SwiftPM locks its own cache, so a shared one is safe.

## 1.12.0 - 2026-11-12 - minor
- DerivedData of its own per job on a macOS node (M22.3): every Mac job gets `$MULEBOX_DERIVED_DATA`, a folder in its job folder, for `xcodebuild -derivedDataPath`, so jobs never share build products and the cleanup removes it with the job (`xcode.derived_data_env`).
- Package caches `cache-spm` (Swift packages) and `cache-cocoapods`, per project like the others: CocoaPods reads `CP_CACHE_DIR`; SwiftPM reads no setting, so the job's log says to pass `$MULEBOX_CACHE_SPM` as `-packageCachePath` or `--cache-path`. Agents' docs, the contract and the skill say how.

## 1.11.1 - 2026-11-12 - patch
- From Sol's review of 1.11.0 (M22.2): the scan asks each Xcode for its runtimes, and a job's simulator is of a runtime its own Xcode can use (the pinned one, else the newest), so a job pinning an older Xcode no longer gets a newer runtime it cannot run.
- The device is the highest model number of the runtime's iPhones (or of its devices), not simctl's first: simctl can list an iPhone XS before an iPhone 16.
- A device list from `simctl` that cannot be read is an error, so the cleanup is tried again, rather than an empty list that counted as removed and left the simulator behind.

## 1.11.0 - 2026-11-12 - minor
- A simulator of its own per job on a macOS node (M22.2): a job with `needs: [simulator]`, or a pinned runtime (`toolchain: {simulator: "iOS 18.2"}`), gets one, made by its script's first lines (`xcrun simctl create mulebox-<job id>`), its id in `$MULEBOX_SIMULATOR`; without a pin, the newest iOS runtime's newest iPhone. A runtime the node lacks exits 5, naming the ones it has (`worker/simulator.py`).
- The cleanup removes it by name on every outcome, before the job's containers and folder, and is tried again if `simctl` fails; a worker that starts removes every `mulebox-job-...` simulator an earlier one left, and no other. With no Xcode nothing is asked.
- The Xcode scan keeps the runtimes it found (with their device types) for the jobs, so choosing one runs nothing in the worker's loop. A Mac with a runtime offers the capability `simulator`; `mulebox doctor` fails a pinned runtime no online Mac has. `xcode.parse_runtimes` is gone: one parser, in simulator.py.

## 1.10.1 - 2026-11-12 - patch
- From Sol's review of 1.10.0 (M22.1): a job that pins an Xcode takes it from the worker's last scan, so a claim no longer runs `xcode-select` (twice, up to 10 s each, in the worker's loop); a bundle removed since the scan counts as missing. Before the first scan has finished, the node is looked at once, as before.
- A pin and an Xcode's own version are one release with trailing zeros aside (`16.2` is `16.2.0`), in the job and in `mulebox doctor` (`versions.same_release`).

## 1.10.0 - 2026-11-12 - minor
- Xcode as a toolchain on a macOS node (M22.1): a project pins one, `toolchain: {xcode: "16.2"}`, and its job gets that Xcode's `DEVELOPER_DIR`; mulebox does not install Xcode, so a version the node lacks exits 5 before anything runs, naming the versions it has (`worker/xcode.py`).
- A Mac worker reports its Xcodes (every `/Applications/Xcode*.app` and the one `xcode-select` points into), their SDKs and the available simulator runtimes beside its toolchains, from a scan beside its loop every 5 minutes (one `xcodebuild` per Xcode can take seconds, so a claim never waits on it; a runtime added or a failed probe shows up by the next scan), and offers the capability `xcode`, which a project pinning one needs. `mulebox doctor` lists each Mac's Xcodes, SDKs and simulators, fails a pinned version no online Mac has, and says a job does not install it. The scan beside the loop and the list in doctor came from Sol's review.
- `tests/conftest.py` keeps the tests from reading the dev machine's own Xcode; `command.run` takes an environment.

## 1.9.2 - 2026-11-12 - patch
- CI runs the Python suite on GitHub's macOS machine too (M21.5): a `macos` job on `macos-15` with Python 3.13, beside the Linux matrix, as a Mac can now be a node. A pinned version rather than `macos-latest`, so the machine changes only when we say; tests/test_ci_workflow.py checks the job is there.

## 1.9.1 - 2026-11-12 - patch
- From Sol's review of 1.9.0 (M21.4): the dashboard's metrics imported the service manager's `for_platform` over the machine readings' own, so a dashboard started with no `/proc` given would have failed to sample; the two are now kept apart, with a test.
- A runner's agent group on a Mac is signalled only when launchd's pid leads a group and runs the agent's own `run.sh`, so a reused pid is never paused; a resume that cannot reach a running agent is an error and is tried again, not taken as done.
- Whether a run is alive on a Mac: the line must start with the runner's own `bin/Runner.Worker`, so a folder with a space in it still matches and a `tail -f` of that file does not. The agent's group is asked of launchd once and kept while it lives, rather than every round.

## 1.9.0 - 2026-11-12 - minor
- GitHub runners on a macOS node (M21.4): each is a launchd agent, `mulebox-runner-<name>`, which runs the runner's `run.sh` as the systemd template does (`RUNNER_MANUALLY_TRAP_SIG`, kept alive, 5 min to stop, `nice 5`), written by `services/launchd_runners.py`. `runner add` downloads the `osx-arm64` or `osx-x64` runner and checks it against its own checksum in the release notes.
- A runner's service goes through `mulebox/services/` on both systems (`runner_check|start|stop|restart|state|freeze|boost|group`), so `runner add|list|remove|caches`, pause and boost, and the worker's supervision no longer call `systemctl` themselves; `runner list` says `running` or `stopped`. On Linux the same commands run as before.
- On a Mac, whether a run is alive is read from `ps` (no /proc), its CPU from the agent's process group and the engine's numbers for its containers, its memory in the dashboard's jobs' memory too; pause stops the agent's group (SIGSTOP), and a stop or restart continues it first. A first process that leads no group of its own is never signalled as a group. Boost raises only the run's containers there.

## 1.8.2 - 2026-11-12 - patch
- From Sol's review of 1.8.0 (M21.3): a job's CPU on a Mac counts its exited children (`ps -S` adds a reaped child's time to its parent), so a build of many short compiler runs no longer reads as idle; one `ps` listing serves every job of a round, with a 3 s limit, so a slow `ps` holds the worker loop up once rather than once a job.
- The kernel's host port is taken once rather than at every sample, which added a reference to it each time; the 32-bit tick counters of each core are unwrapped, so a wrapping one no longer reads as an idle machine.
- The engine's socket follows the `docker context` in use (`DOCKER_CONTEXT` included) before the usual socket, so with Colima chosen beside Docker Desktop the readings come from the engine that runs the containers. A container whose memory the engine does not give makes the dashboard's jobs' memory unknown, not smaller.

## 1.8.1 - 2026-11-12 - patch
- From Sol's review of 1.7.0 (M21.2): a worker that restarts on a Mac stops a job's process group only while its first process is still the recorded one; a group whose first process is gone, or that `ps` cannot read, is left alone (a group id is reused, so it could be another program's), and the record kept when `ps` failed.
- A job's command waits behind a gate until its record is on disk, so a worker killed in between leaves a shell that exits 75 and runs nothing; a record that cannot be written refuses the job.
- `common/safefile.py`: small files written and read relative to a folder descriptor from safepath (`open_dir`), never through a symlink. The job records use it, and so do the runner folder's files and reservation, which had their own copies.
- One `signal_group` for both executors: EPERM (a group of unreaped exited processes on macOS) counts as gone for running jobs too, not only for orphans. A stop sends SIGCONT after SIGTERM, so a frozen job can take it. A stop blocks for the grace time as `systemctl stop` does on Linux; that stays.

## 1.8.0 - 2026-11-12 - minor
- Readings on a macOS node (M21.3): `common/host.py` gives the machine's cores, memory, swap and network the same way on both systems, from `/proc` on Linux and from macOS itself (`common/darwin_host.py`: the kernel's core counters through ctypes, `vm_stat`, `vm.swapusage`, the `en*` interfaces of `netstat`). The load a worker reports, its activity meter and the dashboard's graphs read through it; on Linux nothing changes.
- A job's own readings on a Mac: its process group's CPU and memory from one `ps` listing, each process keyed on its own so a new one counts from nothing (`worker/darwin_jobs.py`), and its containers' CPU, memory and traffic from the Docker engine's API (`worker/docker_stats.py`), asked beside the loop. Anything unknown stays unknown, never idle. The dashboard's jobs' memory sums the recorded groups and the containers.
- `common/docker_socket.py`: one place that finds the engine's socket, `DOCKER_HOST`, `/var/run/docker.sock`, else the docker context (Colima), for the dashboard and the readings.

## 1.7.0 - 2026-11-12 - minor
- Jobs on a macOS node (M21.2): `worker/darwin_exec.py` builds on the process-group executor. Each job leaves a record of its group in `<staging>/job-groups/` (through safepath), so a worker that restarts finds and stops the groups an earlier one left, and a record whose group id now belongs to another process is only removed. Jobs run under `nice -n 5`, the Mac's counterpart of a unit's lower CPU weight; boost reaches only a job's containers there, as only root can raise a priority again. A group of exited, unreaped processes (EPERM on macOS) counts as stopped.
- Pinned Node.js installs the build for the node's own system (`node_build`: `linux-x64`, `darwin-arm64`); `download.linux_arch` is now `cpu_arch`, beside `system_name`.

## 1.6.1 - 2026-11-12 - patch
- From Sol's review of 1.6.0: a launchd agent is looked for in both the screen session (`gui/<uid>`) and the background one (`user/<uid>`), so one loaded over ssh with nobody at the screen is still restarted, stopped and moved after someone logs in, never left running beside a second copy.
- install.sh, with no `MULEBOX_PYTHON`, takes `python3` only if it is 3.12 or newer, else the newest `python3.14`, `python3.13` or `python3.12` on PATH: Homebrew's `python@3.13` installs `python3.13` alone, and a Mac's own `python3` is older.

## 1.6.0 - 2026-11-12 - minor
- A Mac can hold mulebox's services (M21.1, the user's ask): `mulebox service install|restart|stop|status|logs` drives systemd user units on Linux and launchd agents on macOS (`mulebox/services/`). install.sh accepts macOS (Homebrew's folders on PATH, `xcode-select` and `brew` hints, bash 3.2) and hands the services to `mulebox service install`, so the bundle no longer carries `systemd/`. Every message and doc names `mulebox service ...` rather than `systemctl` or `journalctl`; the upgrade waiter starts through the same module. `common/command.py` runs short system commands for both.

## 1.5.0 - 2026-11-12 - minor
- An isolated runner can run several jobs at once (the user's ask): `--count N` on `runner register --isolated` and `runner add --isolated` makes a group of places, `<name>`, `<name>-2`, ..., each with its own container, slot and tool cache. Registering again with a larger count adds only the missing places, so the existing one keeps its warm cache; removing the runner removes the whole group. mulebox's own CI ran its three jobs one after another, 4m 28s warm against about 1 min on GitHub's machines.

## 1.4.4 - 2026-11-12 - patch
- Roadmap: M23.6 done. mulebox's own CI passed on its isolated runner, 4m 28s warm with its three jobs one after another; the first run took 20 min, most of it downloading Python 3.13 and Node 22 into the new runner's tool cache over the node's link.

## 1.4.3 - 2026-11-12 - patch
- A CI card on an isolated runner said "Cores: measuring" for its whole run (the user's report): the meter read the runner's systemd service, which a runner in a container does not have. It now reads the job's container, found from the runner's marker, its id asked of Docker once per container.

## 1.4.2 - 2026-11-12 - patch
- Found by mulebox's first CI run on its isolated runner: the two matrix jobs of one run share their run, attempt, job name and runner name, so the second found the first's finished reservation and was failed ("ended (passed) before it got a slot"). An isolated runner now sends a reservation key of each job's own, from its one-job runner's name. A host runner running two matrix jobs one after the other has the same key; not changed here.
- The test of the container's hook ran the real script with a refusal, and under a real runner it found the `Runner.Worker` running the tests among its parents and killed it ("mulebox: refused"). The test's copy now looks for a name no process has.

## 1.4.1 - 2026-11-12 - patch
- mulebox's own CI runs on the node (the user's ask, M23.6): the owner's own runs of `ci.yml` go to an isolated runner, `mulebox-ci`, and a fork's pull request or any run another account started stays on GitHub's machines, so a contributor's CI still runs. The release stays on GitHub's machines. The repository variable `CI_RUNS_ON` moves the owner's runs back with no code change. The rules test and docs/releasing.md now allow exactly that route and nothing else self-hosted.
- Drilled on a throwaway private repository first: a job with checkout and setup-python passed in its container with no Docker socket, no capabilities, `sudo` refused, only its three folders mounted and the dashboard out of reach; the second run took 31 s, setup-python 0 s from the tool volume. With the runner's accounts set to another name, the run failed in 13 s with no step run, `if: always()` included, GitHub showing mulebox's reason, and the next run passed. `runner unregister` left no container, folder, volume or runner on GitHub.

## 1.4.0 - 2026-11-12 - minor
- Isolated runners, the second layer for public repositories (the user's ask, M23.6): `mulebox runner register --isolated` (or `runner add --isolated` on the node) runs every GitHub job in a fresh container, removed when the job ends: no folder of the node, no Docker socket, no capabilities, `no-new-privileges`, limits on memory and processes, half the CPU weight and a network of its own. No token: the node's `gh`, signed in as the repository's admin (the user's call over a token file), makes a one-job runner per job (`generate-jitconfig`), whose configuration goes in on stdin. The image is GitHub's runner image with git, curl and shellcheck, built once per runner release, so a job starts in about 10 s; a tool cache volume per runner keeps setup-python and setup-node downloads. The container's hook hands the job's GitHub values and event to the node, which runs the guard and reserves the slot outside the job's reach; a refusal kills the job in its container. Pause and boost act on the container. A slot still awaited when its container ends is given up, so the next, idle container never holds it. `runner list` shows `isolated`, `runner remove` takes no token. A plain runner still refuses a public repository.
- Fixed from Sol's review before release: each round gets its own `io` folder and waits out a decision still in flight, so a late "allowed" for one job can never reach the next (a guard bypass otherwise); the runner's `_diag` files are opened one folder at a time, never through a symlink and only as regular files, with bounded reads (`runners/diag_files.py`, for host runners too), so a job cannot make the node copy its own files, such as its `gh` sign-in, into a log, or block it on a FIFO; a round cleans up whatever fails (container, unused one-job runner, slot, marker), and removes its container even when only the `docker` client died; files the container's user wrote are given back to the node's user before they are deleted (worker/reclaim.py); `runner remove` stops the runner's rounds first and waits for the current one to end; a runner's one-job runners on GitHub are found by exact name, so removing `build` never touches `build-fast`'s.
- Docs: install.md, README, agents.md, design.md and interfaces-m3.md say what an isolated runner needs (Docker, the node's `gh` as admin), what a job gets, and what it does not cover (a shared kernel, the network beyond the firewall, no Docker in jobs).

## 1.3.0 - 2026-11-12 - minor
- The guard, the first layer for running public repositories on mulebox's runners (the user's ask, M23.6): every runner's job-started hook now refuses a fork's pull request, a follow-on run of one, a run started by a comment on a pull request and a job with no readable event file or metadata, before it holds a slot and before any step, container or Docker build of the job runs. A failed hook alone lets later `if: always()` steps run (Sol's review, read in StepsRunner.cs), so a refusal also kills the runner's `Runner.Worker`. It fails closed (Sol's second review): it runs before the node's config is read and finds its runner from the hook's own path, a missing or unreadable `.mulebox-runner.json` refuses every job, a job whose process it cannot find is held in the hook, and the hook script kills the job when mulebox fails in any other way, reading its parent from /proc or ps and waiting it out when it cannot tell (Sol's third review); a held hook ends with the job's process, leaving nothing behind. The reason is written to the job process's stderr before the kill, so GitHub shows it as the failed job's annotation (its own log is never uploaded). Proven on a real runner of a throwaway private repository: an `if: always()` step never ran on a refused job. `runner add` on the node now needs `--actors`. `runner register` records the account `gh` is signed in as (`--actors` to name others), and the hook refuses a run any other account started or re-ran. Read in GitHub's runner source first: the hook runs before anything of the job, and its environment cannot be set by the workflow. Fork rules after runner-up's fork guard. Public repositories stay refused until the second layer, a fresh container per job (design.md).
- Docs: what a runner needs on GitHub (admin rights, `gh auth login` as that account), in install.md and the README.

## 1.2.4 - 2026-11-12 - patch
- The release workflow skips files PyPI already has (`skip-existing`). Re-pushing the tags v1.1.1 and v1.2.0 in UTC this morning ran it again, PyPI refused the files it had ("400 File already exists"), and the repository showed its pypi deployment as failed, though both releases were on PyPI. A new version still uploads; a test holds the setting.

## 1.2.3 - 2026-11-12 - patch
- The docs test reads a repeated heading's anchor as GitHub writes it (`-1`, `-2`, ...): README's link to its second "The dashboard" (`#the-dashboard-1`, from 1.2.1) works on GitHub but failed the test. CI had skipped the docs-only commit and caught it on the next full run.

## 1.2.2 - 2026-11-12 - patch
- Roadmap: M23, safer and fairer jobs (the user's ask), ten tasks to start after the macOS phases: isolation per project, job sizes in place of fixed slots, order rules, node priority levels, a failing node rests, fresh CI runners, upgrades on trial, usage against size, config reload, and a slot reserved for yourself.

## 1.2.1 - 2026-11-12 - patch
- Docs: a "Why mulebox" section near the top of the README (the user's ask): what sets mulebox apart in seven points (made for agents, the working copy sent as it is, Compose projects, tools an agent uses alone, one line for agents and CI, the dashboard and controls, upgrades in line), each linking to its part of Features.

## 1.2.0 - 2026-11-11 - minor
- One pair of names everywhere, the user's call: the **dev machine** (where you and your agents edit code: a laptop, a desktop or another Linux PC) and the **node** (a Linux machine that runs jobs), in place of "laptop" and "build machine". In the docs, CLI help and messages, the contract, the skill, the dashboard and the architecture images. Not renamed: protocol and database fields, example hostnames such as `laptop.local`, the laptop icon on a job's card, and past entries here and in phases.md. Anchors to install.md's section 2 are now `#2-install-on-the-dev-machine`.

## 1.1.5 - 2026-11-11 - patch
- A change to docs alone runs no tests, the user's call: CI skips it (`paths-ignore` in ci.yml: the root docs, LICENSE, VERSION, `docs/**/*.md` and `.html`), and `mulebox check` gives back the last passed result (`ignore_changes:` in `.mulebox.yml`, the same list). `tokens.css` and the packaged SKILL.md stay code. A test keeps the two lists equal and code out of them; AGENTS.md and releasing.md say so.

## 1.1.4 - 2026-11-11 - patch
- Docs: a README section, "Give every machine a fixed address": mulebox keeps each machine's address (the laptop's config, a worker's coordinator, the LAN dashboard), so an address the router changes after a reboot or reconnect makes the machine unreachable. It names a DHCP reservation, a static address or a stable name, and how to recover; install.md, getting-started.md and troubleshooting.md point to it (the user's ask).

## 1.1.3 - 2026-11-11 - patch
- Docs: releasing.md names 1.1.1 as the first release on PyPI, and the roadmap's M17.4 records how the release went and what is still open. 1.1.2 changed nothing in the package and is not released (the user's call).

## 1.1.2 - 2026-11-11 - patch
- release.yml: a comment read "No token or password: PyPI trusts ...", which GitGuardian took for a password with the value "PyPI" (a false alarm on 1.1.0; nothing secret was ever in it). Reworded so it no longer reads as a setting.
- Released: 1.1.1 is the first mulebox on PyPI, published by the release workflow; installed from PyPI with `uv tool install` (uv's own Python 3.12) and with pipx on the Mac, each holding the dashboard. The unpublished 1.0.0 draft release was deleted (the user's call); its tag stays.

## 1.1.1 - 2026-11-11 - patch
- A test of UDP port probing failed once in GitHub's CI (on 1.0.1): the random UDP port's TCP side was held by something else on the shared machine. The test now picks a port whose TCP side is free.

## 1.1.0 - 2026-11-11 - minor
- mulebox goes to PyPI, the user's choice: `uv tool install mulebox` (uv brings its own Python) or `pipx install mulebox` with Python 3.12 or newer. The release workflow checks the tag against VERSION, builds the dashboard and the wheel, installs and runs it, and publishes it by trusted publishing (environment `pypi`); `tools/pypi_readme.py` points the README's links at the tag for PyPI's page. The binaries are dropped (`tools/build_binary.py`, the `binary` extra): macOS kills an unsigned binary a browser downloaded, and there is no Apple Developer ID.
- Upgrade messages name the command: `mulebox/common/upgrade.py` says `uv tool upgrade mulebox`, `pipx upgrade mulebox` or `git pull` from how mulebox was installed, used by `doctor`, `skill update`, the dashboard's version notice and the protocol error; a machine is upgraded with `mulebox setup <host>`.
- docs/releasing.md: a release is made when the user says so, at the version `main` is on; 1.1.0 is the first on PyPI. Install, getting-started and the README follow; the README's status says 1.x and stable. Reviewed by a second model (gpt-6.1-sol), whose points were fixed.

## 1.0.1 - 2026-11-11 - patch
- The 1.0.0 release: CI and the release workflow passed on `v1.0.0`; both binaries were downloaded from the draft and run (macOS with no Python on the path, listing the real build machine; Linux on the build machine), and the wheel was added. The release is published by the user.
- install.md: the macOS binary has an ad-hoc signature, not an Apple Developer ID, so macOS kills it when a browser downloaded it; `xattr -dr com.apple.quarantine` fixes that, checked on a copy given the browser's mark.

## 1.0.0 - 2026-11-11 - major
- mulebox 1.0.0, declared by the user: the first public release. Commands, `.mulebox.yml` and the
  config files are now stable; a change that breaks them needs 2.0. In daily use on a real build
  machine with real projects and their CI; the repository went public the same day, after the
  history scan, rewrite and cleanup (roadmap M6.4). Binaries for macOS on Apple silicon and Linux
  on x86-64 come from the release workflow on the `v1.0.0` tag; the macOS one was built and run
  against the real build machine first.

## 0.107.0 - 2026-11-11 - minor
- `feedback_off` in `client.toml`: a list of projects whose problems `mulebox feedback post` never posts, such as one that belongs to a client, as the feedback repository is about to turn public (the user's call). The agent is told to tell the user instead; agents.md, design.md, the feedback guide and the config example say so.

## 0.106.6 - 2026-11-11 - patch
- README: the package caches said plainly (the user's ask): packages download once per project and the next job, a fresh container or the project's CI runner installs from the node, with the measured pnpm and Composer runs.

## 0.106.5 - 2026-11-11 - patch
- The docs give mulebox's real address, `typerhack/mulebox`, in place of `example-org/mulebox` (install lines, the agent-install prompt, releases, the feedback repository example); AGENTS.md rule 6 names it as the one exception (the user's decision).
- README: GitHub runners attach to private repositories only, said plainly with the reason (a fork's pull request runs its own workflow on your machine), and that open-source projects can use GitHub's hosted runners.

## 0.106.4 - 2026-11-11 - patch
- README: a full Features section in place of "What it does" (the user's ask): agents, speed, real projects, GitHub Actions, steering jobs, machines and projects, the dashboard, machines and safety, each feature checked against the roadmap and code.
- `mulebox runner unregister` (`runner remove`) clears the runner unit's failed state, which systemd otherwise went on listing; seen when this repository's own runner was unregistered before going public.
- History rewritten (the user's call): every commit's time zone is +0000 with the same moment, and a project name in two old tests is `example-app`; roadmap M6.4 updated.

## 0.106.3 - 2026-11-11 - patch
- README: the architecture picture is centred (the user's ask).

## 0.106.2 - 2026-11-11 - patch
- README: the architecture picture in the design system's colours, light and dark (`tools/architecture_svg.py` draws both from tokens.css), in place of Mermaid's own colours; a prompt to let a coding agent install mulebox from getting-started.md; every everyday command with what it does; "What it does" regrouped and widened from a second opinion by another model (job ids, no duplicate runs, GitHub runners on the same line, caches, toolchains, browser tests, secrets kept out), saying plainly that a node restart interrupts a running job.
- agents.md no longer says an attached job is cancelled 5 minutes after its client goes; since M18.1 every job runs to its end.

## 0.106.1 - 2026-11-11 - patch
- The sign-in page's field and button are 44px on touch screens and under 520px, as every control of the app since 0.103.1; it already used the design system's tokens and fonts in both themes.
- README: opening the dashboard from a phone, with the sign-in page in both themes and the four steps to turn `lan` mode and its password on; `tools/screenshots.py` takes the sign-in page too.

## 0.106.0 - 2026-11-11 - minor
- `mulebox setup` installs the agent skill in every Claude config folder on the laptop that has none, as well as updating old copies (the user's ask); `--no-skill` installs none. install.md, getting-started.md and the README say so, with a link to SKILL.md and how the newest skill comes with the newest mulebox.
- README: commands name `<node>`, explained once, in place of `build-1`; the architecture as a Mermaid diagram (the user found the text drawing hard to read), the dev machine on top, the coordinator node handing jobs to worker nodes below.

## 0.105.0 - 2026-11-11 - minor
- README as a product page (the user's ask): a two-step install near the top, the architecture in the dev machine and node terms (the coordinator holds the line and the dashboard, workers ask it for jobs), and ten screenshots: the queue in both themes, a job and a GitHub run, machines, history, statistics, the compact CPU view, a phone and the design system's reference page.
- `tools/screenshots.py` takes those pictures from the dashboard's stand-in data in headless Chrome; `MULEBOX_MOCK_CLEAN` leaves the stand-in's out-of-step notices out, and its machines report the checkout's own version.

## 0.104.1 - 2026-11-11 - patch
- Tests: the project-pause tests use `example-app`, the docs' sample name, in place of a name that echoed a real project. A scan of the whole history before going public found no addresses, MAC addresses, host or user names, home paths, keys or tokens beyond made-up test values.

## 0.104.0 - 2026-11-11 - minor
- The CPU box has two views (the user's idea): details, a meter per core as before and the default, and compact, an All meter, the busiest cores by number (six, or four below 1101px, kept steady until another core is 10 points busier) and one line for the others with their average and highest. A small switch beside the box's note changes it, remembered per browser, shown only when compact would hide a core. Seen on the stand-in API with 32 cores: the box kept the Machines box's height at 1440px, and at 390px nothing was cut or scrolled sideways.
- `MULEBOX_MOCK_CORES` sets the stand-in machine's core count for `npm run dev`.

## 0.103.3 - 2026-11-11 - patch
- Roadmap parking lot: the dashboard's overhead is back to 0.60% of a core and 46 MB, and the mockup's facts now on the dashboard are crossed off (job folders of other machines and log line times stay); the user's idea of a compact CPU view beside today's box is parked until they confirm it.

## 0.103.2 - 2026-11-11 - patch
- A GitHub run's Time panel marks the run with its own result (failed, cancelled, passed, or released for an older slot with none); a failed run showed a pass mark. Found in a real CI drill on the deployed dashboard, where each step's length and result showed as built in 0.102.0.

## 0.103.1 - 2026-11-11 - patch
- Controls on touch screens and under 520px are 44px high, up from 36px, as Apple's guidance asks (the user's choice); design-system.md has nothing left open before building.

## 0.103.0 - 2026-11-11 - minor
- The Memory and Disk boxes show, for the dashboard's own machine, what the mockup asked for (parking lot): memory used by jobs, as the working set (`memory.current` less droppable page cache) of job units, of runners busy with a GitHub job and of both's containers; swap; and Docker's disk use (`GET /system/df`, every 5 minutes). On the build machine they add under 0.1 ms of CPU a second.

## 0.102.0 - 2026-11-11 - minor
- A GitHub run's page shows each step's length, live while it runs, and its result (passed, failed, cancelled or skipped) with its icon, from the runner's own diary (parking lot): the worker writes `mulebox: step at <time>: <name>` and `mulebox: step <result> at <time>: <name>` into the slot's log, and older logs still read. Checked against real runner diaries on the build machine (passed, skipped and cancelled steps).

## 0.101.3 - 2026-11-11 - patch
- design-system.md, "Open before building": control sizes measured on the deployed dashboard (28 to 34px with a pointer, 36px on touch, under the 44 to 48px of platform guidance; raising it is the user's call); frozen and boosted cards, Resume and End boost, the waterfall and the live log recorded as settled.

## 0.101.2 - 2026-11-11 - patch
- Dashboard overhead (parking lot): the queue, read every second, sorted every finished job to keep the last 20, 9.7 ms of 12.6 on the real store of 1273 jobs. An index `jobs_finished (state, finished_at, seq)`, made when the coordinator opens its store, brings that query to 1.5 ms. An installed package's version is read once per process, not on every machines read (about 1 ms each).

## 0.101.1 - 2026-11-11 - patch
- `test_events_follow_a_real_job_through_the_queue` starts the first job once `events` has printed its first line, not after a fixed 0.8 s: on the loaded build machine it missed the #2 line and failed the gate.

## 0.101.0 - 2026-11-11 - minor
- `mulebox runner register` refuses a public repository before asking for a token, as docs/install.md already said never to attach one: a fork's pull request brings its own workflow file. `unregister` still works there.
- ci.yml's comment no longer says this repository keeps no runner: it has one for drills while private, to remove before it goes public (docs/releasing.md, M6.4).

## 0.100.2 - 2026-11-11 - patch
- Roadmap: M14.13 done, every item of a GitHub run's menu drilled on a real CI run in Edge, Cancel on GitHub through `gh` on the build machine.

## 0.100.1 - 2026-11-10 - patch
- Roadmap: M14.1 and M14.10 done (the React dashboard on the real machine in Edge, the classic page retired); the facts with no API data yet and the dashboard's overhead go to the parking lot.

## 0.100.0 - 2026-11-10 - minor
- History page (the user's ask): live search on project, job or branch (300 ms after typing stops, no Filter button) and the Statistics filters plus job name and result, kept in the address and while paging. `/api/history` takes `project`, `job`, `client`, `worker`, `kind`, `result` and `q`, all in SQL (dashboard/history_query.py), 400 on a bad value, and lists the filters' choices on its first page from the same list the Statistics page uses; both pages share one `FilterSelect`.
- Checked: web lint, types, 42 tests and build; the full suite through `mulebox check` (2760 passed); in real Edge on the stand-in API at full width and 390 px in both themes.

## 0.99.0 - 2026-11-10 - minor
- The classic dashboard page is retired (the user's call): the React build is the only front end. The lan sign-in page is part of it, in Gauge, with only it, its stylesheet and the fonts open before signing in; with no build, `/` answers 503 with how to build it, and the API keeps working. `mulebox setup` stops, naming Node.js and npm, when the build is missing or out of date and npm is not there.
- A waiting row in the Jobs box says which job holds its branch, as `mulebox queue` does (`branch_busy`).
- The line-count check skips `.claude/` (agent worktrees, git-ignored).
- Checked: web lint, types, 36 tests and build; the full suite through `mulebox check` (2759 passed); in real Edge on a local lan dashboard with a throwaway password: the sign-in page in both themes, a wrong password's message, signing in, and the 503 page with no build.

## 0.98.0 - 2026-11-10 - minor
- Jobs box (the user's pick of three, option A, with a second model's refinements): a machine's lane with running and waiting jobs shows the cards on the left and the line on the right, each under a heading (one column under 760 px, two cards side by side when each can be 280 px wide); a line of more than 6 shows its first 5 and "Show all waiting (N)", positions kept.
- Statistics colours (the user's pick of three, option 3): chart series are a muted teal and ochre palette (`--chart-1` to `--chart-6` in tokens.css), the ochre on marks and swatches only, in place of a blue and orange foreign to the theme.
- design-system.md: chart rules, the lane layout, and the 4/8/12 gaps and the meter switch settled from "Open before building"; specimen and mockup colours updated. Stand-in API scenes `MULEBOX_MOCK_SCENE=split|wide`.
- phases.md: the dashboard controls drilled in real Edge on 0.97.0, and the overhead measured against the classic page.

## 0.97.0 - 2026-11-10 - minor
- The dashboard front end in React (M14.10 with M14.1): `web/`, React 19 with Vite, TypeScript and Tailwind CSS locked to the design system's tokens (tokens.css imported by path, Tailwind's own palette and scales left out, `npm run lint` fails on a typed-in value). Radix menus and tooltips, Lucide icons, Geist bundled. Layout "Monitor on top" in Gauge: every view and control of the classic page, plus the Machines page, a clicked machine shown in CPU, Memory and Disk, the meter style switch (Auto, Gauge, Rainbow) and a GitHub job's log as its steps.
- Served by the same aiohttp process: `/` is the React build when the package holds one (`mulebox/dashboard/app/`, not in git), the classic page stays at `/classic/`, and without a build `/` is the classic page (dashboard/pages.py). The policy gained `font-src 'self'` for the bundled fonts.
- `mulebox setup` builds the front end before the wheel when it is out of date (client/webbuild.py); without npm it says so and goes on. CI has a `web` job; the release workflow builds it before the binary.
- Checked: lint, types, 32 unit tests and the build; the Python suite through `mulebox check` (2750 passed); in real Edge against the real dashboard read only, and with made-up data at 1912, 1440 and 390 px, both themes, both meter styles, 2 and 20 machines. Bundle JS 419 kB (132 kB gzip), CSS 31 kB (7.5 kB gzip).

## 0.96.0 - 2026-11-10 - minor
- Other machines' readings for the dashboard (M14.10, so a clicked machine fills CPU, Memory and Disk): workers send per-core CPU, memory totals and their fullest disk inside `load` with claims and heartbeats, from the same 2 s sample, no extra process; a claim's `disk_free` reuses that reading. Disk usage is shared in common/disk.py (`usage_by_device`, `fullest`). The coordinator checks each new field and keeps it in `workers.load`, schema unchanged (20). The dashboard keeps up to 5 minutes per worker from its existing 2 s machines read (dashboard/machine_history.py); `GET /api/metrics?machine=<name>` answers for the host, for another worker (empty while offline), or 404 (dashboard/metrics_api.py). `/api/machines` rows gain `host` and `version`. Full suite passed through `mulebox check` (2735 passed).

## 0.95.5 - 2026-11-10 - patch
- Design system: several machines (the user's pick, "click a row"): the top row shows the host by default and any machine clicked in the Machines box, never changing size; lanes only for machines with work; a Machines page. The reference mockup is updated with it.

## 0.95.4 - 2026-11-10 - patch
- Design system: a third meter style, Auto, the default: Rainbow in the light theme, Gauge in the dark one (the user's choice).

## 0.95.3 - 2026-11-10 - patch
- Design system: two meter styles, Gauge (one solid fill) and Rainbow (the old dashboard's teal to amber to red ramp, segmented), chosen per browser beside the theme switch; the ramp colours are tokens in tokens.css. The user's choice after seeing both.
- The dashboard layout the user picked, "Monitor on top", kept as docs/design-system/dashboard-mockup.html for M14.1 and M14.10.

## 0.95.2 - 2026-11-10 - patch
- A job of a paused or held project no longer holds a GitHub run back: it keeps its place in line but may not start, as a paused job already did (reservations.ahead). Found on the real machine, where a CI run waited with both slots free behind three jobs of paused projects.

## 0.95.1 - 2026-11-10 - patch
- A GitHub run's service goes back to weight 50, its unit's own, after a boost and at a worker start; 0.95.0 set it to 100, found on the real machine. The cancel item asks "Yes, cancel the run", not "Yes, cancel on github".

## 0.95.0 - 2026-11-10 - minor
- A GitHub run's card and waiting row get the three dots, as agent jobs have (the user's ask): open its page, open on GitHub, and once it runs Freeze or Resume and Boost or End boost; its page gets the same buttons. The worker's runner supervisor applies them to the runner's service and its Compose containers (runners/runner_controls.py, reusing worker/controls.JobControls), and thaws and sets the service back when the run ends; the coordinator allows them on a running slot only (job_control.py). A long freeze can make GitHub fail the run; the user chose to have it.
- Cancel on GitHub: from the card's three dots or the run's page, the dashboard asks GitHub with `gh run cancel` on its machine (runners/cancel_run.py); `gh` must be logged in there. Before, the dashboard refused it.

## 0.94.0 - 2026-11-10 - minor
- A design system, Gauge (M14.12): docs/design-system.md with its rules, docs/design-system/tokens.css as the one source of token values, and specimen.html as the picture. The user picked it from three proposals (Stable, Signal, Gauge) made by a Fable subagent and reviewed by a second model. Its open points are listed for the React front end (M14.10).
- AGENTS.md rule 10: every screen follows the design system and takes its values from tokens.css. CLAUDE.md, README, design.md and the roadmap link it.
- The line-count check skips the top-level docs/ folder, as its docstring and AGENTS.md already said docs are exempt; the specimen is a 695-line HTML picture.

## 0.93.4 - 2026-11-10 - patch
- CLAUDE.md: any UI work loads Anthropic's frontend-design skill first, whatever the model, subagents included (the user's rule).

## 0.93.3 - 2026-11-10 - patch
- Roadmap: M14.3's last open check passed: a real waiting CI slot moved up from its arrow in Edge and took the next free slot ahead of a job queued before it.

## 0.93.2 - 2026-11-10 - patch
- Roadmap: M14.8 no longer lists the real failure and the CI card's cores as open; both were seen on 2026-11-10.

## 0.93.1 - 2026-11-10 - patch
- Roadmap: M14.3 notes that moving GitHub's waiting slots (0.91.0) is covered by tests only so far.

## 0.93.0 - 2026-11-10 - minor
- Dashboard: a Statistics page (`#/stats`, M14.11), design A of the three the user was shown: filters by type, project, source and machine; today and all time side by side with the split between mulebox jobs and GitHub Actions; the last 14 days as stacked columns; one table by project, type, source, machine or job name. From `/api/stats`, so it shows what `mulebox stats` shows; checked against it in real Edge on the real history.
- `stats` days carry their seconds per kind (`kinds`), for the chart; before, the split of a past day was not known.
- `drawOutline` in format.js: stroked outline icons on a 24 grid.

## 0.92.1 - 2026-11-10 - patch
- `mulebox stats --kind ci` failed: a body field named `kind` clashed with `request()`'s own argument; that argument is positional-only now. Found running it on the real history.

## 0.92.0 - 2026-11-10 - minor
- Job minutes (M14.11, the user's ask): `mulebox stats` shows how long jobs ran today, day by day and since the first job, with a breakdown by project, job, source (a laptop or GitHub), machine or kind, and the same filters. One module, `coordinator/stats.py`, behind the new `stats` request and the dashboard's `/api/stats`, so both give the same numbers. Wall time added up; running runs count to now and are given apart, runs with no length are counted as unknown, runs are cut at midnight. Rules in design.md, Job minutes. The page comes next, from a design the user picks.

## 0.91.1 - 2026-11-10 - patch
- A running card reads "12m 11s usually 13m": without "of", a job of ten minutes or an hour also keeps its time on the card's first line. Measured in real Edge on a real card at 280 px.

## 0.91.0 - 2026-11-10 - minor
- GitHub runs' waiting slots move in line like any job: arrows on their waiting row, and Move items in their three dots (`mulebox first|up|down|last` too). Nothing else about them is steered, as GitHub owns the run. Asked by the user.
- The line is one order for both kinds: a slot's turn and the check that holds agent jobs behind a slot now follow moves (`store.line_key`, shared with upgrades); before, both went by arrival time alone, so moving a job ahead of a waiting slot did not really put it ahead.
- A paused job keeps its place without holding a GitHub run's slot back.
- A running card's "of usually" figure is to the minute (seconds in its tooltip), so it fits on the card's first line beside the time (the user's report).

## 0.90.4 - 2026-11-10 - patch
- Docs caught up with the day: README (steering the queue, queued upgrades, adding a machine), design.md (project pause and queued upgrades in the queue), interfaces-m2.md (three-dots menus, Queue actions, state icons, wait reasons).

## 0.90.3 - 2026-11-10 - patch
- Dashboard: the Jobs list keeps its scroll position when the queue redraws; before, any change in the queue threw a reader back to the top. Found in the M14.3 drill.
- A running card's "of usually" time does not break inside itself.
- Roadmap: M14.3 done in real Edge on real jobs.

## 0.90.2 - 2026-11-10 - patch
- Dashboard: a frozen, paused or boosted job shows small icons beside its state (snowflake, pause, bolt; the words as tooltip and for screen readers), not words that broke the card's layout (the user's review).
- `mulebox queue` no longer marks every moved job "first": the position column already says the order.
- Wait reasons on the dashboard without command backticks; "The machine takes jobs again" in Queue actions.

## 0.90.1 - 2026-11-10 - patch
- Dashboard: freezing, pausing, boosting or moving a job now reaches open pages; the queue's change check left those fields out, so a frozen job's card did not say so until something else changed. Found in the M14.3 drill in Edge.
- Dashboard: waiting rows give the coordinator's own reason (paused, a paused project, behind an upgrade, the machines held), the one `mulebox status` gives; before, only "no machine fits" showed.

## 0.90.0 - 2026-11-10 - minor
- Pause whole projects: `mulebox project pause <name>... [--minutes N]`, `resume`, `paused`. None of a paused project's jobs or GitHub runs starts, they keep their place and say why, and the rest of the queue goes on; a pause ends by itself (60 min by default, a day at most). Wire message `project_pause`. Asked by the user, to keep real projects off the machine during drills.
- Job cards and waiting rows have the three dots again (the user's call: the "Actions" button broke a card's layout), bolder and on the same line as the time; "Queue actions" keeps its words.

## 0.89.3 - 2026-11-10 - patch
- A running card keeps "of usually" beside its time (0.89.2 hid it, against M14.6); the Actions button goes under the time when the card is narrow.

## 0.89.2 - 2026-11-10 - patch
- Roadmap: M14.10, the dashboard front end in React with Vite, built at release time and served by the existing server (the user's choice; Next.js left out).
- Actions menu a little wider so hints wrap less; a running card's time stays on one line beside its Actions button.

## 0.89.1 - 2026-11-10 - patch
- Actions menus, after the user's review: a bordered "Actions" button with a chevron on each card and row (the dots were hard to see), "Queue actions" beside the tabs instead of on the box border, and every item with an outline icon, a bold name and one line on what it does, grouped, listing only what applies now.
- The page draws its controls once its token arrives; before, a quiet queue showed no menus or arrows after a reload.
- A job behind an upgrade says so (`waiting_for`), and the upgrade says what it waits for; the dashboard shows such reasons plainly, keeping the red "stuck" badge for jobs nothing can run.
- Roadmap: M16.5 done on the real machine.

## 0.89.0 - 2026-11-10 - minor
- Queued upgrades (M16.5, the user's idea): `mulebox setup <machine> --queued` sends the new version and returns; on the machine it is a row in the line, "mulebox upgrade to X", next by default (nothing new starts there, the running jobs end, it installs, the line goes on) or `--behind` the jobs already waiting. A waiter unit on the machine asks for its turn and installs; the installed mulebox reports the result and the installer's output as the row's log. It shows in `mulebox queue` and on the dashboard, moves and cancels like a job while it waits, cannot be cancelled while installing, and lets the machine go 90 s after its waiter disappears. Wire message `upgrade`, allowed for worker keys.

## 0.88.1 - 2026-11-10 - patch
- Jobs box: a frozen, paused or boosted job says so on its card and waiting row; before, only its page and `mulebox queue` did.

## 0.88.0 - 2026-11-10 - minor
- Reorder the line (the user's ask): `mulebox up|down|last <job-id>` beside `first`, and four outline arrows (to the front, up, down, to the end) on every waiting job in the dashboard's Queue tab and on its page. A move writes the new order into every waiting job's priority, so jobs sent later still come after them. `normal` now only ends a boost and keeps the job's place.
- A "more actions" menu (dots) on every running card and waiting row in the Jobs box: pause or freeze, resume, the moves, boost, open its page, cancel (asked twice). One in the Jobs header acts on everything: pause or resume all machines, freeze all running jobs, resume all paused jobs.

## 0.87.1 - 2026-11-10 - patch
- Out-of-step strip and header mark: the warning triangle and the danger circle are outlines now, a round stroke in the level's colour with no fill (the user's ask: the filled shapes looked muddy), and the light theme's amber for them is brighter (`--warn-mark`).

## 0.87.0 - 2026-11-10 - minor
- Dashboard controls, on by default on the tunnel and the LAN address with or without a password (the user's call: mulebox is a tool for the owner's own network): a job's page has Pause or Resume, Run first or Back in line, Boost or End boost beside Cancel; each online machine has Pause or Resume. They send the CLI's requests through `mulebox rpc`; Origin, Host and a page token still keep other web pages out. `controls = false` takes them away; `cancel_button` is read and ignored.

## 0.86.0 - 2026-11-10 - minor
- Steer jobs (M14.3, the user's ask): `mulebox pause|resume|first|boost|normal <job-id>` and `machine pause` (drain). A paused waiting job keeps its place and does not start; a paused running job is frozen on its machine (systemd freezer, docker pause) and is not asked or stopped as stuck, and resuming answers what was asked. `first` moves a waiting job ahead; `boost` gives a job the top CPU and disk weight and keeps its machine from taking new jobs. Schema 20 (`jobs.paused`, `priority`, `boost`), wire message `job_control`.

## 0.85.1 - 2026-11-10 - patch
- Roadmap: M14.2 and M14.8 done, runner caches run on a real runner (M20.3).

## 0.85.0 - 2026-11-10 - minor
- Dashboard: each machine in the Machines box has a `net` line under its cpu and mem meters, its network in and out as the worker reports it (M14.2, the user's pick of placement).

## 0.84.2 - 2026-11-10 - patch
- A runner's restart (`mulebox runner caches`) left its old listener running beside the new one: the unit stopped run.sh alone (KillMode=process), and run.sh passes a stop on only with RUNNER_MANUALLY_TRAP_SIG. The unit now sets that and KillMode=mixed. Seen on a real runner: the old listener, without the new cache settings, took the next CI job.

## 0.84.1 - 2026-11-10 - patch
- Roadmap: M14.9 done in full (the mark at 390 px), M14.2 built, M5.3 blocked on a second worker.

## 0.84.0 - 2026-11-10 - minor
- Workers report their machine's network in and out (KiB/s) with every claim and heartbeat, over its physical interfaces only (common/netdev.py), so a VPN tunnel and Docker bridges do not count the same bytes again; `mulebox machine list` shows them and the dashboard's machine rows carry them (M14.2, no schema change: `workers.load` is JSON).

## 0.83.7 - 2026-11-10 - patch
- Dashboard: on narrow layouts, where the page scrolls, the header is sticky, so the out-of-step mark stays in sight as designed; it had scrolled away with the page (seen at 390 px in real Edge). Its click puts the strip below the header, not under it.

## 0.83.6 - 2026-11-09 - patch
- Docs: setup's target is whatever `ssh` takes (alias, address, user@address); troubleshooting lists setup's three login messages and what to do for each; roadmap M14.9 notes the light theme seen.

## 0.83.5 - 2026-11-09 - patch
- mulebox setup names why the login failed: an unknown host name asks for an address or an ssh config entry, an unreachable machine asks for its network and ssh server, and only a refused login gets the key advice.

## 0.83.4 - 2026-11-09 - patch
- The warning triangle (out-of-step strip, header mark, warn results) has rounded corners and a rounded mark with a round dot; the sharp one with a square cut-out looked crude at 15 px in both themes.

## 0.83.3 - 2026-11-09 - patch
- Roadmap: M14.9 (out-of-step strip) done, M14.8 progress, and M20 for the issues agents filed (#1 to #11).

## 0.83.2 - 2026-11-09 - patch
- install.sh sets a runner's CPU share with a plain if, not A && B || C, which shellcheck flags; the repository's CI failed on it, while the build machine, which has no shellcheck, skipped that test.

## 0.83.1 - 2026-11-09 - patch
- The out-of-step strip has two levels: danger in red with a crossed circle for a worker on another mulebox (jobs can fail), warning in amber with a triangle for a laptop or its skill; bigger icons, a faint tint, and a mark with the count in the header that stays in sight and brings the strip back into view.

## 0.83.0 - 2026-11-09 - minor
- The dashboard warns when installs are out of step: a strip above the panels names a laptop on another mulebox than the build machine, a laptop whose skill is out of date, and a worker on another mulebox than the coordinator, each with the command that fixes it. Laptops now say their mulebox version and skill state with every submit, kept per laptop in a new clients table (schema 19).

## 0.82.0 - 2026-11-09 - minor
- The mulebox skill keeps itself current: mulebox contract, the first thing every copy tells an agent to run, says on stderr when an installed copy differs from this mulebox's (not only a lower contract schema, which missed the 0.77.0 text change), and the skill tells the agent to run mulebox skill update and read it again. mulebox setup <host> also updates out-of-date copies on the laptop at its end, so the skill moves with every upgrade. Agents may now update the skill; doctor and the contract say so.

## 0.81.1 - 2026-11-09 - patch
- mulebox run --take says a small file's size in bytes; a 6-byte file read "0.0 KiB" in the first real run.

## 0.81.0 - 2026-11-09 - minor
- mulebox run --take <path> brings a file the command changed back into the project once it passed, such as a lockfile from composer update, so the package manager no longer has to run on the laptop (issue #4). The worker sends the files to the coordinator in chunks before the result (taken), the client fetches them (take) and writes them in place; paths stay inside the project, no symlinks, no secrets or excluded files, 16 MiB each. Schema 18 (jobs.take); kept a day.

## 0.80.0 - 2026-11-09 - minor
- mulebox runner caches <runner> --project <name> points a GitHub runner at the project's package caches, so the gate and CI on one machine download through the same cache; --off undoes it (issue #8).

## 0.79.0 - 2026-11-09 - minor
- ignore_changes: in .mulebox.yml lists paths that are sent but not fingerprinted, so a changelog or docs edit keeps a passed result: no stale warning, and check gives the result back without a five-minute rerun (issue #2).

## 0.78.0 - 2026-11-09 - minor
- mulebox run --bare runs the command alone: no containers, install or setup, so a one-off curl no longer starts MySQL, builds an image and prints the project's setup output (issue #5). In the contract as one_off_bare; report_a_problem now names mulebox feedback guide.

## 0.77.1 - 2026-11-09 - patch
- The notice about env: entries a job goes without is printed only for a job with containers or ports of its own, and says what it means; a lint job with neither printed it every run (issues #6, #9).
- A compose: false job no longer inherits a top-level install that runs docker compose, docker exec or docker run, which could not work without containers; docs say the order install, setup, command, and that a cd in setup stays there, fixed in 0.71.0 (issue #3).

## 0.77.0 - 2026-11-09 - minor
- mulebox feedback draft takes several job ids and puts them in the draft with each job's result, stages, CI step and the mulebox that ran it; --title (default the summary's first sentence), --grep for numbered log lines with context, --log-lines, -o FILE (issue #10).
- mulebox feedback guide prints the whole reporting procedure: when to report, what evidence to gather, how to take out private data the scrub cannot see, ask before posting. The skill points to it; a second skill was weighed and dropped, as the guide in the CLI cannot fall behind the tool.
- The scrub keeps what identifies nobody: loopback addresses, links to public package registries, package@version, and the word github; post names each refused line and the kind of thing found, never the value (issue #11).

## 0.76.0 - 2026-11-09 - minor
- GitHub jobs get their real result: GitHub does not give the completed hook the job's status, so all 129 earlier reservations were stored as passed. The hook now reads it from the runner's own diary (runners/diary.py), with the first failed step and GitHub's message on it, stored as jobs.ci_result (schema 17). Checked against 124 real runs. Older reservations still show released.
- Dashboard: CI jobs appear in the Failed and Passed tabs; a failed one says which step failed and why; every finished job's state has a mark (check, cross, warning, stop) in tables, history and on its page (marks.css).
- A CI card's CPU counts the Compose containers started from the runner's work folder: a real backend test step in a container used all 8 cores while its card read 0.0. Background polling for Docker is shared with the agent job meter (background.Polled).

## 0.75.4 - 2026-11-07 - patch
- Roadmap: M5.2 marked done (its check passed in 0.74.1).

## 0.75.3 - 2026-11-07 - patch
- mulebox init on a plain Python project: pytest found from test_*.py or the requirements, a --check given as python or pytest runs from setup's venv, and a note when .venv is not git-ignored; from a newcomer agent's trial on a blank machine.
- Setup's login error says how to make a key, copy it as another user and accept the host key, without a double period; getting-started.md lists what to ask a person for once; the contract no longer says setup runs before every job.

## 0.75.2 - 2026-11-07 - patch
- Dashboard: a running job's card follows its stage, step and CPU live; the queue event fired only on state changes, so a long job's card kept what it showed at its start until a reload.

## 0.75.1 - 2026-11-07 - patch
- Roadmap: M5.2 key removal seen for real; M5.3 readings seen from a second worker.

## 0.75.0 - 2026-11-07 - minor
- Workers report their machine's CPU and memory with every claim and heartbeat (schema 16); the dashboard shows them for every online machine, and mulebox machine list too (M5.3). The /proc readers moved to common/proc.py.

## 0.74.1 - 2026-11-07 - patch
- status and events say when every machine that can run a queued job is draining, and how to resume one; roadmap M5.2 done.

## 0.74.0 - 2026-11-07 - minor
- mulebox machine list, drain, resume and remove: a drained machine finishes its jobs and takes no new ones, a stopped one can be forgotten with its key taken off the coordinator; the dashboard shows draining (schema 15, M5.2).
- docs/install.md: how to take a machine away and how to move the coordinator.

## 0.73.1 - 2026-11-07 - patch
- Roadmap: M5.1 done, a blank second machine joined with setup --worker-of and took jobs while the first was busy.

## 0.73.0 - 2026-11-07 - minor
- mulebox setup <worker> --worker-of <coordinator> adds a build machine: a key made on the worker, let in on the coordinator only for a worker's requests (ssh-gate, authorize-worker), and a worker-only node.toml from the installer (M5.1).
- The cluster holds as many jobs as its online workers have slots, never fewer than the coordinator's own slots; before, a second machine would get no work while the first was busy.

## 0.72.1 - 2026-11-07 - patch
- Roadmap: M8.9, M13.1, M18.4 and M19.10 done, from two real projects' jobs and files.

## 0.72.0 - 2026-11-07 - minor
- mulebox init follows the project's CI: its compose files (COMPOSE_FILE or -f in .github/workflows, else CI and test overlays by name) and its Node version, a major pinned as the newest release of it; Composer and PHP tests run in the compose service built from their folder; split into init_ci, init_files and init_langs (issue #1).

## 0.71.0 - 2026-11-07 - minor
- From a project's report: a cd in setup no longer carries into the job's command (exports still do); GitHub runners get the same CPU share as mulebox jobs, set in place on running ones; docs for install: false with compose: false, a MySQL healthcheck over TCP, and runner jobs without the machine's job_env.

## 0.70.3 - 2026-11-07 - patch
- Docs, from a project's report: containers a CI workflow starts itself get Docker's 1024 open files, corepack over pnpm/action-setup on a slow link, and why a CI job can take longer than mulebox check.

## 0.70.2 - 2026-11-07 - patch
- A card's word for a job's command stage is 'running', short enough for a narrow card.

## 0.70.1 - 2026-11-07 - patch
- A job's CPU is sampled every 10 s, not 30, so its card follows what it does now; a card with no stage yet says starting; a waiting row's usual time has its space back.

## 0.70.0 - 2026-11-07 - minor
- A running job's card says what it is doing: its stage in words (a CI job's GitHub step) and a meter of the cores the job alone uses, pulsing only while it uses half a core or more; CI jobs get their CPU from the runner's service.

## 0.69.5 - 2026-11-07 - patch
- A source checkout reports the version in its VERSION file: an editable install's metadata kept the version it was installed at, so the laptop read 0.68.0 on 0.69.4 and agents were warned of a difference with the build machine.

## 0.69.4 - 2026-11-07 - patch
- Roadmap: M14.6 done, checked in real Edge on the real dashboard.

## 0.69.3 - 2026-11-07 - patch
- Roadmap: M14.7 done, checked on a real CI run.

## 0.69.2 - 2026-11-07 - patch
- A CI job's page no longer repeats every step from the job's own record, and gets its last step: a released slot takes its runner log for a minute more.

## 0.69.1 - 2026-11-07 - patch
- A CI job's step output now reaches its page: the runner names a step's output files after the job's plan id, not its job id, seen on a real run.

## 0.69.0 - 2026-11-07 - minor
- A CI job's page shows its steps live and each step's output once the runner writes it, read from the runner's own files by the worker and redacted like any log.

## 0.68.2 - 2026-11-07 - patch
- Dashboard: the GitHub and laptop icons are 15 px at full strength, sized on the icon itself; at 12 px and 80% they were hard to see.

## 0.68.1 - 2026-11-07 - patch
- Dashboard: a card's usual time sits on the line of its timer, so cards with and without one stay the same height.

## 0.68.0 - 2026-11-07 - minor
- Dashboard: a job card shows where the job came from (GitHub's mark for CI, a laptop and its system for an agent), a CI repository without its owner, and how long such a job usually takes beside its time.
- A CI job's page says its output is on GitHub instead of showing an empty log. Its GitHub link opens in a new tab. The client sends its system with a job (store schema 14).

## 0.67.1 - 2026-11-07 - patch
- M19 checked on the real machine; `docs/agents.md` says how to copy a browser a machine cannot download.

## 0.67.0 - 2026-11-07 - minor
- A run that lost a connection while fetching images or packages no longer counts in `usual` (store schema 13).

## 0.66.13 - 2026-11-07 - patch
- Installing a pinned toolchain tries a lost network 3 times, and if it stays lost the error says so instead of suggesting another version; a 404 is not retried.
- `mulebox status` warns when a job fetching things printed a lost connection last.

## 0.66.12 - 2026-11-07 - patch
- pnpm's `Downloading x: a MB/b MB` lines go from logs, keeping its `, done` line; one real log had 589 of them.
- Installing a pinned toolchain is a stage of its own, `toolchain` (contract schema 15), not hidden in `prepare`.

## 0.66.11 - 2026-11-07 - patch
- A service a job builds has `pull_policy: build`: its tag is the job's own, so the pull Compose tried could only print `pull access denied`.

## 0.66.10 - 2026-11-07 - patch
- `mulebox run --in <service> -- <cmd>` runs a one-off command inside a compose service (contract schema 14).

## 0.66.9 - 2026-11-07 - patch
- `mulebox queue` says why a queued job waits, as `status` does: a branch taken, or the machines busy.
- The contract drops `take_it_back`, a second name for `its_result` (contract schema 13); the dashboard's question names `mulebox ok`.

## 0.66.8 - 2026-11-07 - patch
- `mulebox feedback draft` keeps a whole title: only GitHub's own limit cuts one now, not 100 characters.

## 0.66.7 - 2026-11-07 - patch
- `doctor` no longer says a machine offers a toolchain it has yet to install; the next line says the first job installs it.

## 0.66.6 - 2026-11-06 - patch
- A repeat answered from an earlier result no longer says "submitted" or links the dashboard, as no job started.

## 0.66.5 - 2026-11-06 - patch
- `mulebox init` in a git worktree names the project after the repository, so its worktrees share one project on the machine.

## 0.66.4 - 2026-11-06 - patch
- `check` no longer gives back a failure from an older mulebox: it may have been a fault in mulebox that is gone, as a real trial found after an upgrade. A pass stays a pass. A job records the worker's version (schema 12).

## 0.66.3 - 2026-11-06 - patch
- A project's folders on the machine are readable by others, as on any checkout, so a container's own user can read what a project mounts. They were made 750, the mode of mulebox's private folders, and a database's init folder failed with `Permission denied`. Existing folders open on the next job; the project home above them stays closed. Found by the second agent trial.

## 0.66.2 - 2026-11-06 - patch
- A job's facts fold away under "Job details", closed by default, so a long command no longer stands between the stages and the log.

## 0.66.1 - 2026-11-06 - patch
- The failure summary keeps every failed part of a gate: compiler, type and lint errors now read as failures, a line naming a failed part goes before the details, and forty errors in one part cannot hide another. Found by the first agent trial, where a type error was missing from the summary. Roadmap: M19, what the trial found.

## 0.66.0 - 2026-11-06 - minor
- Watching a job to its end, the page goes back to the queue after 10 s, so the next job shows. It offers to stay, and leaves a log being read alone.
- A job's page says how it went at the top: an icon and a word, with its stage, exit code and end time once it is over.
- A browser asks for the dashboard's files again after each load, so an upgrade reaches it without a forced reload. Found when Edge kept running the old script.
- Runs of one job can be told apart: their ids start alike, so the job page and the queue show the id's end, and the job page the branch and start time.

## 0.65.0 - 2026-11-06 - minor
- The live job page: a connection that dies with no error is noticed and reopened where it stopped, on the log and on the page's own stream. Both streams send a `beat` event a page can see, which replaces an SSE comment it could not.
- A job that writes nothing says so: how long it has been quiet and whether it is working. `/api/jobs/{id}` has `activity` while a job runs.
- Scrolled up in the log, new output shows a button to jump to the latest. Stage clocks tick each second, and catch up at once when a tab comes back.

## 0.64.2 - 2026-11-06 - patch
- `docs/agent-trial.md`: a test plan and report format, so an agent can try mulebox on a real project with no skill installed.

## 0.64.1 - 2026-11-06 - patch
- Roadmap: M2.5, M11.2, M15.1, M15.2, M16.1 and M16.3 closed by real jobs; M16.2 built, with the warning itself seen in tests only. Holding no slot during an install was dropped, with the reason.

## 0.64.0 - 2026-11-06 - minor
- `install:` in `.mulebox.yml`, a stage of its own: it runs in the project's image, is reused until what it depends on changes, also in a compose job, is tried again on a lost network, and if it fails the job exits 5. Schema 11, contract schema 12.
- With an `install` or `setup`, a job turns off pnpm's check before each `pnpm run`, also in containers.
- `mulebox warm [job]` runs a job up to its command.

## 0.63.0 - 2026-11-06 - minor
- `mulebox setup <host> --when-idle` waits for running jobs and upgrades, with new jobs and CI runs waiting in line through a machine-wide hold that ends by itself. New request `drain`.
- A worker reports the free space of its fullest disk (schema 10). Under 10 GB, `doctor` and every command from a project warn and name `mulebox project clean`.

## 0.62.3 - 2026-11-06 - patch
- Roadmap: M11.6 closed by a real reboot with a job running and a detached job queued. No fault found; the dashboard waited for its network address and started by itself 16 s after its first try.

## 0.62.2 - 2026-11-06 - patch
- Roadmap: eight open items closed by short real jobs: failure summary on a compose job, `wait` on a queued and a failed job, expired logs, Composer and npm caches, Mongo's open files, log cleanup on a copy of real history, a passing per-job `setup`. No fault found.
- M11.6 narrowed: a restart with jobs open passed, a real reboot stays open, and workers older than 0.37 and 0.40 are dropped, as none exist.

## 0.62.1 - 2026-11-06 - patch
- A clean machine found that jobs need git there, which nothing said: the installer now checks for it and says how to install it, and the docs list it. The clean-machine run passed, in two throwaway containers.

## 0.62.0 - 2026-11-06 - minor
- Three ways to install the client: pipx, a downloadable binary that needs no Python, or by hand. `tools/build_binary.py` builds the binary as a folder, as a single file took 10 s to start on macOS, and a version tag builds them on GitHub into a draft release. `mulebox setup` works from inside a binary.

## 0.61.1 - 2026-11-06 - patch
- Roadmap: what `mulebox init` writes ran as real jobs for an npm and a Python project.

## 0.61.0 - 2026-11-06 - minor
- A job's pinned node or pnpm installs itself the first time, in the background, so the other slot, heartbeats and cancel go on. A version that will not install exits 5 with the reason and what the machine has. `mulebox doctor` no longer calls it a failure. Installs get the machine's `[job_env]`, as a real pnpm install timed out without its `NODE_OPTIONS`. Contract schema 11.

## 0.60.0 - 2026-11-06 - minor
- `mulebox setup <host>` installs or upgrades a build machine in one command: it checks the login, stops if jobs are running, sends a wheel of the running package, finds out what the machine offers, writes the laptop's config and proves it with a first job.
- The installer files moved into the package (`mulebox/machine/`), so a pip-installed client can install a machine. `tools/deploy.sh` is gone, as `mulebox setup` does its work.
- The installer turns lingering on itself where the machine allows it, and `mulebox node-offers` fills an empty `capabilities` list.

## 0.59.0 - 2026-11-06 - minor
- `mulebox projects` shows each project's folder and size. `mulebox project clean` removes branch folders unused for 14 days, `mulebox project reset` removes a project's or a branch's folder; both only list what would go until `--yes`, and a project is held so no job starts in a folder being removed.
- Roadmap: M18.6 closed after real jobs on three branches and two compose jobs at once.

## 0.58.0 - 2026-11-06 - minor
- Jobs of different branches run at once: a new install has 2 slots, and a finishing job holds only its own slot. A job waiting for its branch names the job in the way (`branch_busy`, contract schema 10).

## 0.57.1 - 2026-11-06 - patch
- A job's result arrives about 5 s sooner: the worker checks every 0.05 s while a job finishes and every 0.5 s otherwise, not every 1 s, and the client no longer waits 2 s on a pipe an ssh control master holds open. Roadmap: M18.5 closed.

## 0.57.0 - 2026-11-06 - minor
- `setup` also reruns when a version file or manifest changes (`VERSION`, `go.mod`, `.nvmrc` and the like): the gate caught an install that had stored an old version.
- A snapshot over 1 MiB sends only the files that changed since the project's last upload: the link to a build machine can do 0.4 MB/s, which made the upload slower than the job's start. The coordinator rebuilds and checks the whole snapshot, and any trouble sends it whole.

## 0.56.0 - 2026-11-06 - minor
- A project now has one folder on the build machine, with a git worktree per branch, and jobs run there instead of starting from nothing: ignored files such as `node_modules` stay, and only changed files are written.
- `setup` is skipped when its text, the toolchain, the env and the lockfiles are unchanged and nothing it may have made was lost. A compose job always runs it.
- Two jobs of one branch run one after the other, even with a free slot. New optional root `projects`, beside `jobs` when left out.

## 0.55.2 - 2026-11-06 - patch
- A stuck job's stop follows the job's own `timeout_min`, not a fixed 30 minutes, so `timeout_min` is the one setting a project needs.
- A job's result names its commit, so an agent told a result can see what it was for. Roadmap: M18.1 to M18.3, M2.7 and M2.8 closed after real runs.

## 0.55.0 - 2026-11-06 - minor
- No more unattended rule: a long job asks its agent, `mulebox ok` answers, a working job always finishes, and only a stuck job with no answer stops. A job also goes on when its client goes away. Store schema 9, contract schema 9.
- Results wait for an agent that went away, and its next command says so.
- `mulebox check` does not repeat a job on the same files: it gives the result or joins the running job; `--again` forces a run.
- `mulebox init` writes a project's `.mulebox.yml` from its own files, so a new project needs no hand-written config.
- README lists these. Roadmap: M18 first, with project homes in git worktrees next; ideas from real use move in as M14 to M16, M17 tracks easy setup, and the rest of M2.4's `lan` checks are not a priority.

## 0.53.2 - 2026-11-05 - patch
- Roadmap: CI passed on GitHub, and the history rewrite is done.

## 0.53.1 - 2026-11-05 - patch
- Roadmap: tasks seen working on a real machine are closed; the rest say what stays open. A merge marker left in docs/design.md by 0.53.0 is gone.

## 0.53.0 - 2026-11-05 - minor
- Optional cancel button on the dashboard for signed-in users on the lan address, off by default, through `mulebox rpc`.

## 0.52.3 - 2026-11-05 - patch
- Job scripts reach bash as written: systemd no longer expands `${...}` in them.

## 0.52.2 - 2026-11-05 - patch
- The failure summary keeps earlier lines that read as the failure, as a test runner's stack and totals can fill the last lines.

## 0.52.1 - 2026-11-05 - patch
- User docs: getting started, troubleshooting, toolchains, a laptop install that works with current
  Python packaging, a warning against runners on public repositories, and the release process.
- CI on GitHub-hosted machines with a read-only token and pinned actions, safe for a public repository.
- `check` and `doctor` say plainly that a repository needs a commit; before, the coordinator's
  refusal read as a field error (exit 4).

## 0.52.0 - 2026-11-05 - minor
- Security review: fork pull requests stay off self-hosted runners; README and install docs state
  the security model.
- Sign-in attempts sent together get no extra guesses; the dashboard redacts a job's setup line;
  `lan_address` cannot be the any-address or loopback.
- Redaction covers more key names, colon forms, token shapes and secret-named `job_env` values;
  more secret files stay out of snapshots.
- The roadmap and an interface doc no longer name projects or a machine.

## 0.51.4 - 2026-11-05 - patch
- Roadmap: the Jobs box is reviewed in real Edge and deployed; a real phone stays open.

## 0.51.3 - 2026-11-05 - patch
- The job view marks the stage the rest of mulebox calls failed: `failed_stage` in the job detail,
  from the one rule in `common/status.py`. A job that never started had a green `images` stage,
  and a cancelled job's stage read as failed. Seen in real Edge.

## 0.51.2 - 2026-11-05 - patch
- The job view's stage bars were empty: the page's security policy refuses a style attribute, so
  they now go through `.style`. Their CSS class also collided with the queue's `.lane` and
  flattened the Jobs box since 0.50.0. Both seen in real Edge.

## 0.51.1 - 2026-11-05 - patch
- A test of `logs --summary` no longer depends on the folder it runs from: the repository now has
  a `.mulebox.yml`, which made the client look up warnings. Found by the first run through mulebox.

## 0.51.0 - 2026-11-05 - minor
- mulebox's own tests run through mulebox: `.mulebox.yml` in this repository, `mulebox check` runs
  them in parallel on the build machine. `needs: [cache-pip]` keeps Python downloads between jobs.
  `.claude/` is ignored, so worktrees stay out of a snapshot.

## 0.50.0 - 2026-11-05 - minor
- The dashboard's job view shows the job's stages as a waterfall: where each ran, how long it took,
  what is usual, what it fetched, and the failing line, live while the job runs.

## 0.49.2 - 2026-11-05 - patch
- `needs: [playwright]` turns off Playwright's own browser cleanup. It removes any browser whose
  project folder is gone, and a job's checkout always is, so each job deleted the browsers of the
  jobs before it. Read off Playwright 1.62's source and a real job's log. A stall may also last
  2 minutes before a retry, not 30 s.

## 0.49.1 - 2026-11-05 - patch
- A failure summary whose last lines show a lost connection or lookup says that it reads like a
  network failure. The texts moved to `common/network_errors.py`, shared with `pull_failure.py`.

## 0.49.0 - 2026-11-05 - minor
- A package cache that starts empty says so in the job's log. A project that turned a cache on saw
  every package downloaded again, with nothing to explain it. The roadmap records today's real
  checks: stage events, last line, `running_ahead`, the registry check and the idle stop.

## 0.48.2 - 2026-11-05 - patch
- Docs: a newly turned on cache starts empty, and what to expect on a slow connection. The roadmap
  gets the fixes still open from the second project reports.

## 0.48.1 - 2026-11-05 - patch
- The worker's service loop moved to `worker/serve.py`, and the tests of compose jobs that do not
  end by themselves to their own file: both had passed 300 lines. No behaviour change.

## 0.48.0 - 2026-11-05 - minor
- `needs: [cache-npm]` keeps npm's downloads between a project's jobs; `cache-pnpm` was no use to
  an npm project. Contract schema 8 covers this and the new `events` and `status` fields.

## 0.47.0 - 2026-11-05 - minor
- `mulebox doctor` tells whether the build machine can connect to the registries of the project's
  images, through a new `reach` request. It said all was fine with no route to a registry.

## 0.46.0 - 2026-11-05 - minor
- A queued job names the jobs on the machines, `running_ahead`, in `status` and `events`. A job in
  a plain line read `waiting_for: null`, which said nothing about why it had not started.

## 0.45.0 - 2026-11-05 - minor
- A check-in and `status` carry `last_line`, the job's last output, redacted. A check-in named only
  the stage, and `command` is most of a job.

## 0.44.0 - 2026-11-05 - minor
- `mulebox events` has a `stage` event as a job enters each stage, so an agent can follow a job
  without its log. Before, a job's events were only started and finished.

## 0.43.2 - 2026-11-05 - patch
- `usual` counts only runs before the job asked about, and of two middle runs takes the lower. A
  real report: `status` on an old job compared it with itself and later runs, and two runs of
  312 s and 349 s gave 331 s, which neither took.

## 0.43.1 - 2026-11-05 - patch
- Roadmap: M13.2 done, after a real job with an unreachable registry exited 5 on a build machine.

## 0.43.0 - 2026-11-05 - minor
- What can stop an unattended job as idle is now the job's own activity, from control groups: its
  unit's CPU, and its labelled containers' CPU and traffic. A real drill showed the machine's
  readings never got near idle with a desktop and a VPN, so a stuck job always ran to 24 hours.
  `status` shows the job's CPU beside the machine's readings. New: `worker/cgroups.py`,
  `worker/job_meter.py`. A job's own unlabelled `docker run` or `build` counts only by its output.

## 0.42.0 - 2026-11-04 - minor
- `check`, `queue` and `status` say where to see the job on the dashboard, on stderr so `--json` stays clean, and `doctor` lists the address. A job's line links straight to its page.
- The address comes from the build machine (`dashboard` in `submit_ok`, `status_ok`, `queue_ok`, `machines_ok`), via `common/dashboard_address.py`. With only `local` it names `mulebox dashboard open`; when off, or from an older coordinator, nothing is printed.

## 0.41.0 - 2026-11-04 - minor
- The dashboard uses one port: `lan_port` defaults to `port` (8090), not 8443, and may equal it. It stays two sockets, one on 127.0.0.1 and one on the LAN address, so the sign-in rules are unchanged.
- Upgrading a `lan` machine with no `lan_port` set moves it to 8090: run the firewall step again, as the old rule covers the old port. The app's own range check holds meanwhile.
- A test pins that loopback is accepted before the rule that drops other addresses on that port.
## 0.40.9 - 2026-11-05 - patch
- The notice for `env:` entries a job goes without lost its doubled colon and reads right for one.

## 0.40.8 - 2026-11-05 - patch
- A job whose images could not be fetched for a network reason is a job that never ran, exit 5, not
  a failed check with exit 1. `worker/pull_failure.py` reads the images stage's last line. The
  failure summary keeps the worker's reason, which stands after the container logs.

## 0.40.7 - 2026-11-05 - patch
- `mulebox doctor` reads Compose's `!reset` and `!override` tags, in the new `client/compose_yaml.py`.
  A project using them got "could not check" and the refusal check never ran.

## 0.40.6 - 2026-11-04 - patch
- Tests for how a stop ends moved to their own file, as the attendance tests had passed 300 lines.

## 0.40.5 - 2026-11-04 - patch
- The roadmap lists the real-machine checks still missing: the 124 path with an older worker, an
  upgrade or reboot with an open detached job, and exit 5 on an older worker with `ports:`.

## 0.40.4 - 2026-11-04 - patch
- A finished job is always a `finished` event, even if the message also carries a `check_in` or
  `unattended` notice. No coordinator sends such a result today; `events` no longer depends on that.

## 0.40.3 - 2026-11-04 - patch
- A `mulebox cancel` after an unattended stop was asked for, but before the worker acted on it,
  now reads `cancelled` (exit 130), not `stopped: unattended`. From `cleaning` on the stop stands.

## 0.40.2 - 2026-11-04 - patch
- A stop that was due or asked for keeps its reason when the worker is lost around it: exit 76, not
  `interrupted` with 75. The sweep looks at stops before worker leases for that. A worker that
  comes back already stopped the job and cleaned up on its next heartbeat; there is now a test.

## 0.40.1 - 2026-11-04 - patch
- A build machine gets `~/.local/bin/mulebox`, so the command has the same name there as on
  the laptop. A real file of that name is left alone.
- The theme button has a third setting: it steps through system, light and dark and shows
  the current one. System was the default but could not be chosen again once set.

## 0.40.0 - 2026-11-04 - minor
- `ports: [vite]` on a job gives it `MULEBOX_PORT_VITE`, a free port for a process of the job
  itself, such as a dev server a browser test starts, from the pool compose ports use and held
  until the job is cleaned up. The names travel in `env` like the compose list, so the store and
  the protocol stay as they are; a worker older than this refuses the job at the start, exit 5.
- `env:` entries built on another job's port are left out for a job that does not have it.
- Contract schema 7: `job_settings` has `ports`.

## 0.39.0 - 2026-11-04 - minor
- A job in `.mulebox.yml` may be a mapping with `run`, its own `setup` (or `setup: false`) and
  `compose: false`, so a quick job skips containers it does not use. A plain command keeps the
  top-level defaults, and `mulebox run` always does. `env:` entries that need a compose port are
  left out for a job without containers, and `check` says which. Client only: `setup` and the
  compose list already went with every job.
- Contract schema 6 with `project.job_settings`.
- `submit.py` split: what a job is on the wire is in `client/job_body.py`.

## 0.38.0 - 2026-11-04 - minor
- The dashboard warns the user: a warning triangle, the word `unattended` and the time left on the
  job, on its machine in both places, and a count on the Queue tab. A job's page says what happens
  and gives the commands to take it back or end it. The time left counts down in the browser.
- A stopped job reads `stopped: unattended` in the queue, its page and history, with the reason
  on its page, and stays out of the Failed tab. History rows now carry `shown_state`.
- The job page's `Timeout` is now `Check-in every`.

## 0.37.0 - 2026-11-04 - minor
- `timeout_min` is a check-in now, not a hard limit: every `timeout_min` a running job reports its
  time, stage, last output and machine readings, as a `check_in` event and a warning in `check`
  and `wait`. A watched job has no limit; `mulebox status` shows its activity and who watches.
- A detached job nobody watches is unattended. `wait` and `events` take it back, also from older
  clients. Stopped after 15 minutes without output, CPU or network (`unattended_idle_min`) or
  at 24 hours whatever it does (`unattended_max_hours`, queued jobs too), both `[limits]` in
  node.toml and saved to `meta` when the service starts.
- A stop shows as `stopped: unattended`, exit 76, reason in `stop_reason`. On the wire it stays
  `cancelled`, so older peers keep working. 124 only comes from a worker older than 0.37.
- The agent is warned by an `unattended` event, `status`, `wait` and on stderr of any command run
  from the project; `--json` output is untouched. `mulebox queue` and the live view show `!`, a
  line per job and a line on top. `claim_ok` carries `limits: "coordinator"`, without it the
  worker keeps the hard limit. Store schema 8: `stop_reason`, `activity`, `active_at`.
- Contract schema 5 with `time_limits`.

## 0.36.7 - 2026-11-04 - patch
- Docs from real project reports: a hardcoded database address and `network_mode: service:...`,
  Playwright `--with-deps` in a project's own scripts, `COMPOSE_PROJECT_NAME` in CI scripts, and
  git-based checks staying local because a job has no git history. The contract's git section
  says the last one as well.

## 0.36.6 - 2026-11-04 - patch
- `mulebox feedback draft`: the report of a title cut at the first `;` could not be reproduced;
  a test now pins that a title keeps its punctuation. What the code did cut was a long first
  line at exactly 100 characters, in the middle of a word. It now cuts at a word, and the
  summary below the title stays whole.

## 0.36.5 - 2026-11-04 - patch
- Checked that the failure summary follows the container logs: it does, on stderr once the log
  has ended. Only the stale and expired-log lines could still come after it, so they now come
  first and the summary is the last thing printed by `check`, `wait` and `logs -f`.

## 0.36.4 - 2026-11-04 - patch
- The contract's database rule said every name needs `${MULEBOX_JOB_SLUG}`. That is for a
  database a job shares. A database in a compose service of the job is that job's alone, so a
  project's fixed name works; agents.md says the same.

## 0.36.3 - 2026-11-04 - patch
- An `env:` entry using a later one is a config error on the client: exit 2 before any upload,
  from `check`, `run`, `contract` and `doctor`. It used to reach the worker, where the job
  could not start. A name the file does not explain may come from the machine's `job_env`, so
  `doctor` warns and the worker still decides (exit 5).

## 0.36.2 - 2026-11-04 - patch
- `env:` entries are read in file order, as the docs say. They were not: JSON objects are
  sorted on the wire and in the store, so an entry using an earlier one failed whenever the
  names sorted the other way. The client now sends the order as `env_order`, stored beside
  `env` (schema 7) and given to the worker with the claim. An older client sends none and
  gets the sorted order it always had.

## 0.36.1 - 2026-11-04 - patch
- A stage mark counts only at the end of a line: a job printing its own mark mid-line could
  record a false stage and lose the rest of that line (found by review).
- A test pins that `job_env` cannot move a path the worker sets, such as a cache.

## 0.36.0 - 2026-11-04 - minor
- Merged the jobs box redesign, built on its own branch as 0.26.0:
- Jobs box redesigned (M2.8): tabs Queue, Failed, Passed and Recent, each with a live
  count and showing one thing, the choice remembered per browser. One running and one
  waiting job were lost above twenty finished rows; the user could not see what was in the
  queue. Released runner slots and cancelled jobs are neither a pass nor a failure, so they
  are listed under Recent (and History) only, with no tab of their own; the old mixed list
  is gone, because it was the crowding.
- The Queue tab is the queue by machine: a lane per machine with what it runs and what
  waits for it, in real queue order. The queue stays one line: a job sits in a lane only
  when that machine is the one place it can run, jobs several machines could take wait in
  one shared list, and a job no machine fits is shown first as stuck with the
  coordinator's reason. Lanes carry only the machine's name and state beside its jobs:
  slots and capabilities stay in the Machines box, shown once.
- Machines box: a small CPU and memory meter per machine, on the load ramp of the big
  graphs. Rows carry `cpu_pct` and `mem_pct`, null until measured: today only the machine
  the dashboard runs on (its own sampler, matched by the node name); every other machine
  reads "no live data" until workers report their load (M5.3), with no page change needed
  then. The worker and the protocol are untouched.
- Job log: the note beside the log says "connecting", "connected, no output yet", "not
  connected, retrying" or "wrote no output" instead of leaving the box blank. A user saw a
  blank box for a running job with a large log; a browser's limit of about six connections
  per site over plain HTTP can hold the stream back when several tabs are open.
- A theme switch redraws the graphs at once with the new colours; they kept the old ones
  until the next sample.
- Dashboard queue rows carry `needs`, `can_run_on` and `waiting_for` on waiting agent jobs
  (`views.placement`, `needs.capable`); the queue fingerprint sees them, so a capable
  machine going offline redraws the queue.
- Ticking times are keyed by job id, not document order, so a tab or lane can never show
  another job's time.
- A viewer's first queue snapshot is built when it connects. It was the last published
  event, so a viewer opening the page minutes after the last change ticked on from stale
  elapsed times (found in headless Chrome: 15 minutes shown for a job 23 minutes in).

## 0.35.0 - 2026-11-04 - minor
- Merge of the agent tools (0.25.4 to 0.34.0, below) and the worker branch. The worker branch
  used 0.26.0 to 0.32.0 as well; its changes are logged here, under the one number they ship
  with, oldest last. Those commits keep their old numbers in git history.
- Schema: one sequence. 3 -> 4 worker toolchains and version, 4 -> 5 `jobs.detached`, 5 -> 6
  `job_steps`, with the `jobs_project` index. A test takes every old schema to the final one.
  A store left at schema 4 by a build of the worker branch alone lacks the worker columns: start
  that one afresh, this version cannot tell it from the agent tools' schema 4.
- `coordinator/history.py` is gone: `coordinator/usual.py` is the one source of what a job
  usually takes, so the queue estimate now reads the last 20 passed runs (was 10) with stage
  rows (jobs from before stages do not count). The estimate's rule stays in it: same command,
  at least 3 runs. `usual` in a `status` reply now keeps commands apart as well.
- The failed stage is real: `failed_step` reaches `status`, the `result` line and `finished`
  events as `stage`, for a job that ended badly. The failure summary and `events` show it. A job
  that could not start shows the stage it stopped in where its worker sent rows, else `start`.
- `mulebox status` lists a job's stages beside what is usual, without a percentage.
- `compose_policy.check(model, checkout: Path | None, shared=())`. With no checkout a cache
  folder counts as written, and `..` is worked out from the text, so `mulebox doctor` cannot be
  told less than the worker by a path that walks out of a cache or to a socket.
- The expired-log line uses the real default (`DEFAULT_LOG_DAYS`), and a test removes a log with
  the real retention code before reading it through the client.
- The contract (schema 4), the skill and docs/agents.md teach package caches, `job_env` in
  services, open files, stages and `usual`, pull summaries, log retention, and that the
  coordinator and workers are upgraded together.
- Old logs are removed: nothing did before. `[retention]` in node.toml has `log_days` (30) and
  `step_days` (365). The coordinator service sweeps at its start and hourly, through safepath,
  only in the logs folder and only for files named after a finished job.
- Test only: what the rewrite adds to services moved to a test file of its own.
- Image pull progress is collapsed in what is stored and streamed: a real log had over 27,000
  lines of it. Outcome lines and errors stay, and a line says how much has been downloaded.
  The amount is a lower bound and also goes on the stage's row. Compose prints no total
  without a terminal, so there is no percentage.
- `status` replies give `usual`: the median length of a project's job and of each stage over
  its last passed runs, or nothing without history. No percentage: a length from the past
  does not say how far a running job has come.
- Job steps: a new table in the coordinator's store, schema version 4, holds one row per stage
  of a job: start, end, exit code, bytes downloaded, failing line. The worker reports them in
  a new `steps` message; `status` replies list them. The time of a slow job could not be
  placed before. `environment` is a stage of its own, for what mulebox provides.
- A compose job runs `up --no-start` before `up --detach --wait`, so images and services are
  separate stages.
- A compose service with no `ulimits.nofile` of its own gets 65536 open files. A real `mongo`
  service died mid-test with "Too many open files": containers started at a soft limit of 1024.
- `job_env` of a build machine reaches every compose service. It only reached the `docker
  compose` process, so a machine's fix for a slow network missed installs in containers. What a
  service sets itself wins, and a project's `env:` value is the one that goes in.
- Package caches: `needs: [cache-pnpm]` or `[cache-composer]` keeps a project's downloads on the
  build machine between jobs, in `<cache>/packages/<project>/<tool>`. A real job downloaded the
  same 905 packages twice and never reached its check. Opt-in and per project, so a job can
  only affect later jobs of its own project; each log names the cache it used.
- A compose file may mount the job's own cache writable; that is the one such path outside
  the checkout, and an external volume stays refused. After a compose job the worker gives
  what root wrote in the cache back to its own user.
- `mulebox cache list` and `mulebox cache clear <project>` on a build machine.

## 0.34.0 - 2026-11-04 - minor
- `mulebox logs`, `logs --summary` and `wait` say when a job's log has expired, rather than
  printing nothing (M8.10). The job's row keeps `log_size` after the file is gone, which tells
  an expired log from an empty one. The exit code does not change: the job's result is intact.

## 0.33.0 - 2026-11-04 - minor
- `mulebox doctor` checks a project's compose files before any upload, with the worker's own
  policy (M8.9): an external volume, a host network or a writable mount outside the checkout
  fails at once, rather than after the job has waited through the queue.
  `compose_policy.check` takes no checkout for this: this machine's paths say nothing about
  the build machine's, so only what the files show counts. `client/compose_check.py` gives it
  the model `docker compose config` would print, as far as the files show it.

## 0.32.0 - 2026-11-04 - minor
- A job that could not start exits 5, not 1, and its outcome line says so: it ran no project
  code, so it must not read as a failed check (M8.8). `check`, `wait`, `events` and the
  summary all go through `report.exit_code_for`. The contract, docs/agents.md and the skill
  say what 5 means.

## 0.31.0 - 2026-11-04 - minor
- The skill ships inside the package; `skills/mulebox/SKILL.md` is a link to it (M8.7).
  `mulebox skill install`, `update` and `status` handle every Claude config folder:
  `~/.claude`, `~/.claude-work` and `CLAUDE_CONFIG_DIR`. `cp -R skills/mulebox` no longer works.
- SKILL.md states the contract schema it was written for and the contract prints the current
  one (now 3, also raised when the skill must teach something new), so an agent can tell the
  user its skill is behind. It never updates itself. `mulebox doctor` reports it, and a test
  ties the two numbers.
- The contract's first rule is again the one against running heavy work locally; a test holds
  it there.

## 0.30.0 - 2026-11-04 - minor
- While queued, `check` suggests `--detach` once, at position 2 or later or for a job that
  usually takes 5 minutes or more (M8.6).
- A labelled estimate of how long a job runs once started: the median of its last 10 passed
  runs with the same command, from 3 runs up (`coordinator/history.py`), on `status_ok` and in
  `queued` events. design.md promised an estimate the code did not have; it now says what
  there is, and that the time in line is not estimated.

## 0.29.0 - 2026-11-04 - minor
- `mulebox events --job <id> --json`: one JSON line per state change, no log text, resumes a
  dropped connection with nothing repeated, exits with the job's exit code (M8.5). It reads
  the coordinator's `watch` stream through `common/status.py`, so it is not a second event
  source. `watch` takes `log: false`; an older coordinator's log is ignored.
- `mulebox status <id>`: one job's state; `status` replies carry the job's facts for it.
- `status_ok` names the worker of an active job. `check` printed `running` without it.

## 0.28.0 - 2026-11-04 - minor
- `mulebox check --detach` (also `run --detach`) prints the job id once the job is queued and
  leaves it running; `mulebox wait <id>` returns what an attached `check` would have, whenever
  asked (M8.4). An agent sat blocked for the whole job.
- A detached job has no client to lose: `jobs.detached` (schema 5) and the client lease sweep
  skips it. The worker lease, the upload timeout, `timeout_min` and `cancel` still apply.
- A coordinator echoes `detached`; without the echo the client cancels the job and fails,
  because an older coordinator would have ignored the flag and cancelled it minutes later.
- A watch stream cut in the middle of a line, or ended without a result, now counts as a
  dropped connection, so the client reconnects. It failed with exit 4 before.
- `logs -f`, `wait` and the like retry a dropped connection for 30 minutes, and fail at once
  when the machine cannot be reached at all.

## 0.27.0 - 2026-11-04 - minor
- `mulebox doctor`: before any upload, validates `.mulebox.yml`, says whether a machine offers
  the project's toolchain versions and capabilities, and warns when client and machine
  versions differ (M8.3). A missing toolchain showed only after submission.
- Workers report their toolchains and version with every claim (`worker/advert.py`, one call
  in `worker/agent.py`), kept in `workers` (schema 4); a new `machines` request reads them.
  A coordinator too old for it still gives its version through `mulebox version`.

## 0.26.0 - 2026-11-04 - minor
- A failed job ends with a short summary on stderr: stage if known, exit code, and its last
  lines without progress output and container logs (M8.2). `mulebox logs <id> --summary`
  prints it without the log, reading only the tail; `status` replies carry `log_size` for
  that. An agent read a huge log to find one line.
- The worker's two log notes the summary looks for are shared constants in `common/status.py`
  (one line each in `worker/agent.py` and `worker/compose_job.py`).

## 0.25.4 - 2026-11-04 - patch
- A missing toolchain error lists the versions the machine has (M8.1). It only named the
  install command, so an agent had no alternative to offer. Small change in
  `worker/toolchains.py`.

## 0.25.3 - 2026-11-04 - patch
- A template tracked in git (`.env.example`, `.sample`, `.template`, `.dist`) is now uploaded:
  a real project builds `.env` from one in `setup` and could not start without it. Untracked
  templates, real `.env` files and a project's own `exclude` stay out.

## 0.25.2 - 2026-11-04 - patch
- License: MIT, chosen by the user (M6.1). `LICENSE`, the README and the package metadata.

## 0.25.1 - 2026-11-04 - patch
- Docs: M2.7 status after a real compose job under full load on a build machine.

## 0.25.0 - 2026-11-04 - minor
- Dashboard redesigned as a live monitor: boxes that fill the window, per-core meters, CPU
  and memory history, disk meters, machines with slot squares, and one jobs list. The page
  was a task list before; the user wanted to see the machine at a glance.
- One theme over the whole page, with a sun and moon switch remembered per browser. The
  sign-in page follows the system setting, because it may not load scripts.
- Drawing stops while the tab is hidden, and two graphs replace nine.

## 0.24.7 - 2026-11-04 - patch
- Test only: the dashboard snapshot test read an event stream once and sometimes saw two of
  its three events. It now reads until all three arrive.

## 0.24.6 - 2026-11-04 - patch
- Nothing under `/run` or `/var/run` may be bind-mounted from outside the checkout. A list of
  socket paths missed a rootless BuildKit socket in a user's run folder; sockets there have
  names no list can hold.

## 0.24.5 - 2026-11-04 - patch
- The loader names `LD_PRELOAD`, `LD_AUDIT` and `LD_LIBRARY_PATH` are refused only for a
  `compose:` project, the only place with a checked file to protect, and other `LD_*` names
  are not refused at all. 0.24.0 failed ordinary builds that set `LD_RUN_PATH`.

## 0.24.4 - 2026-11-04 - patch
- A service using a name from `build.tags` follows the job's private tag, as one using `image:`
  did. It kept the shared name, so it ran a stale image or pulled an unrelated one.

## 0.24.3 - 2026-11-04 - patch
- The coordinator adds `docker` and `compose-v1` to any job carrying compose files. Only the
  client did, so an older client's job could still reach an older worker.

## 0.24.2 - 2026-11-04 - patch
- A bind or file secret that is a Unix socket is refused by its file type, and a folder holding
  a known runtime's socket by a list: Docker, containerd, CRI-O, podman, k3s, BuildKit. Only
  Docker's was known, and a read-only mount does not stop anyone talking to a socket.

## 0.24.1 - 2026-11-04 - patch
- Devices asked for through `deploy.resources` are refused, as `devices:` and `gpus:` already were.

## 0.24.0 - 2026-11-04 - minor
- Environment names that change how a job starts are refused, on the client and on the worker
  (`common/env_rules.py`): `BASH_ENV` and its like for every job, `COMPOSE_*` and `DOCKER_*` for
  a compose project. `BASH_ENV` ran project code before `up`, which could replace the checked
  file. `up` is the first line of the script, so nothing of the project runs before it now.
- design.md and agents.md say the boundary plainly: this stops a CI file's assumptions from
  reaching past the job, and does not contain a hostile project.

## 0.23.1 - 2026-11-04 - patch
- `tools/drill_compose.py`: a drill against a real Docker daemon, since the tests use a fake one
  and cannot show that generated files make resources teardown can find.
- M4 done, with what passed on a real machine and what was not run, in docs/phases.md.

## 0.23.0 - 2026-11-04 - minor
- `[job_env]` in node.toml: environment for every job on a machine, for what the machine
  needs and no project should have to know. Below a project's `env:`. Node's 250 ms limit per
  address made npm fail near 3 s on a slow network; `docs/install.md` has the setting.
- Troubleshooting says how bridges were fixed in real use, as a NetworkManager setting.

## 0.22.1 - 2026-11-04 - patch
- Port allocation probes the protocol a port is published on. It always tried TCP, so a UDP
  service on the chosen port was missed and the job failed with "address already in use".

## 0.22.0 - 2026-11-04 - minor
- A `compose:` job needs `compose-v1`, which a worker reports by itself. A worker from before
  compose offering `docker` used to claim such a job, ignore the compose file list and run
  its commands against the machine. It is now refused, with "upgrade the build machine".
  Deploy workers before clients.

## 0.21.3 - 2026-11-04 - patch
- Cleanup runs beside the worker's loop. It ran inside it, so a stuck Docker daemon could stop
  heartbeats past another job's lease, and cancels and runner supervision with them. The
  cleaning job heartbeats too, and the worker waits for cleanups when it stops. `compose
  config`, which still runs in the loop, gets a timeout that stays inside a lease.

## 0.21.2 - 2026-11-04 - patch
- A built image gets a tag only its job has, whatever `image:` and `build.tags` say; services
  using that image follow. Cleanup removes that tag by name, without force, not the image
  by id, so a tag someone else put on the same image survives.

## 0.21.1 - 2026-11-04 - patch
- A read-only bind outside the checkout must already exist, and gets `create_host_path: false`.
  Compose would otherwise create the folder on the build machine, and nothing removes it.

## 0.21.0 - 2026-11-04 - minor
- `worker/compose_policy.py` holds what a compose model may not do, and refuses more: `volumes_from`
  outside the project, `container:` namespaces, `uts`, `userns_mode` and `cgroup` on the host,
  `devices`, `cap_add` beyond a short list, `security_opt`, the Docker API, `provider`, `runtime`,
  privileged hooks and builds, non-bridge networks, non-local volumes, and any bind of a
  folder holding the Docker socket. Review found these went straight through.

## 0.20.1 - 2026-11-04 - patch
- M4 status from the real drills: M4.2 done, M4.1 and M4.3 built with what is still open.
  Troubleshooting entry for NetworkManager detaching Docker's bridges, which blocks services
  reaching each other on an affected machine.

## 0.20.0 - 2026-11-04 - minor
- Jobs from `.mulebox.yml` run with `bash -e`. A multi-line job used to report only its last
  line, so failed migrations followed by a passing line counted as passed. A job relying
  on a line being allowed to fail now needs `|| true` on it.

## 0.19.0 - 2026-11-04 - minor
- `needs: [playwright]`: jobs share one browser folder in the cache root, so a browser is
  fetched once per machine. A worker offers the capability once a person has installed the
  system libraries, which takes root. `worker/runspec.py` keeps this out of the agent loop.

## 0.18.0 - 2026-11-04 - minor
- `compose:` works. mulebox merges the project's files with `docker compose config`, rewrites
  the result (`worker/compose_file.py`) and gives the job only that file, through
  `COMPOSE_FILE` and `COMPOSE_PROJECT_NAME`, so `docker compose exec -T` needs no flags.
  Containers start before `setup`, inside the job, so the timeout, cancel and redaction apply.
- Every published port moves to 127.0.0.1 on a port mulebox picks (`worker/ports.py`), named
  by `MULEBOX_PORT_<SERVICE>_<PORT>`, so jobs clash neither with each other nor with what
  else runs on the machine. `container_name` is dropped; networks and volumes are renamed.
- Refused, with the reason: host network, PID or IPC namespace, `privileged`, external
  networks and volumes, volumes on a host device, the Docker socket, writable binds outside
  the checkout.
- A failed job's log ends with the state and last lines of its containers.
- `mulebox contract` has a `compose` key. `config.py` split: `common/config_project.py`.

## 0.17.0 - 2026-11-04 - minor
- Docker cleanup: `worker/docker.py` is the one place that runs the docker CLI and refuses
  `prune` and `system` outright; `worker/docker_cleanup.py` removes only what a listing
  filtered on one job's exact labels returned, and repeats until that listing is empty.
- `worker/reclaim.py`: root-owned files in a job folder are given back to the worker's user
  by a locked-down throwaway container, then deleted through safepath. No sudo. It mounts
  only a folder `safepath.confirm_dir` proved to be inside the jobs root.
- `worker/cleaner.py`: Docker first, folder second, on every outcome, and recovery after a
  crash from both the job folders and the labels. A folder that cannot be removed no longer
  stops the worker from starting.

## 0.16.0 - 2026-11-04 - minor
- A job whose `needs` no worker offers no longer waits forever without a word: it is refused
  at submit with what to change, and a queued job that cannot start says why in
  `waiting_for`, shown by `mulebox check` and `mulebox queue`. Details: docs/interfaces-m4.md.
- `workers.OFFLINE_AFTER_S` and `is_online` moved out of the dashboard, which now shares them.

## 0.15.0 - 2026-11-04 - minor
- `services:` in `.mulebox.yml` is now a config error that says to use `compose:` or `env:`.
  It was parsed and printed by `mulebox contract`, but nothing ever started a service.
  Removed from the contract, whose `schema` goes to 2, and from the design doc's example.
- `compose:` files are checked on the laptop: safe relative names, no repeats, present in
  the project. A `compose:` project needs a worker with `docker`, and may not set
  `COMPOSE_FILE` or `COMPOSE_PROJECT_NAME` in `env:`. Running it comes in a later change.
- `common/compose.py`: the names and filters every Docker step is derived from.

## 0.14.1 - 2026-11-04 - patch
- Docs: README, docs/install.md and the node.toml template now say the LAN password is
  optional. No behaviour change.

## 0.14.0 - 2026-11-04 - minor
- `lan_password = false` turns off the dashboard's LAN sign-in, keeping the code and the
  range and Host rules. Requested by the user; the default stays true. `/healthz` also
  returns `sign_in`, which decides whether the page shows the sign-out button.

## 0.13.0 - 2026-11-04 - minor
- `mulebox projects` (M7.4): every project the coordinator has seen, worked out from its
  jobs. New `projects` message, additive, so the protocol version stays 1; an older
  coordinator refuses it with an error.
- No project registry: it would only be a second copy of `.mulebox.yml` and the job history.

## 0.12.0 - 2026-11-04 - minor
- `mulebox feedback draft` and `post` (M7.3): agents report what mulebox could not handle as
  GitHub issues. Drafting is local; `post` needs `feedback_repo` and refuses a file the
  scrub would still change. Rules: docs/design.md, Agent feedback.
- `common/anonymize.py`: removes names, home folders, email and IP addresses and URLs, on
  top of `redact.py`.
- Screenshots from the original idea are dropped: they cannot be scrubbed automatically.

## 0.11.1 - 2026-11-04 - patch
- `skills/mulebox/`: an installable skill for coding agents (M7.2), which sends them to
  `mulebox contract` rather than copying it. Built here; installing it is the user's step.

## 0.11.0 - 2026-11-04 - minor
- `mulebox contract` (M7.1): tells an agent how this project builds, tests and uses git
  through mulebox. Generated from `.mulebox.yml` and the code's own tables, so there is no
  second copy; needs no network; `--json` has stable keys and a `schema` number.
- `ProjectNotFound`: a missing `.mulebox.yml` and a broken one are now told apart.
- docs/phases.md: new M7 for agent work, starting from the parking lot.

## 0.10.0 - 2026-11-04 - minor
- Dashboard machines panel (M2.6): every worker, online or offline, free slots and what it
  is running. New `GET /api/machines` and `machines` event.
- Job heartbeats now refresh a worker's `last_seen`. Claims stop while a worker is full, so
  a busy machine would otherwise have shown as offline for its whole job.
- Free slots are counted from active jobs, because the stored value is stale during a job.
- `coordinator/workers.py`: worker storage moved out of store.py, which neared 300 lines.

## 0.9.0 - 2026-11-04 - minor
- `lan` mode is now plain HTTP by default; HTTPS is the new optional `lan_tls = true`. User's
  decision: on a trusted home network, a browser warning on every visit is worse than no
  encryption, and installing a certificate on each device is not worth it.
- The password and range rules now follow the listener a request arrived on, not TLS.
  Without this, dropping TLS would have left the LAN port with no sign-in.

## 0.8.0 - 2026-11-04 - minor
- `lan` dashboard mode (M2.4): HTTPS on a configured address with a password, for devices
  on the LAN. The SSH tunnel keeps working. Set up with the new `mulebox dashboard cert`,
  `password` and `firewall` commands. New node.toml keys: `lan_address`, `lan_port`.
- `lan_range` must now be a private network, and `lan` mode is IPv4 only.
- Self-signed certificate marked CA, because phones only fully trust those, with name
  constraints so it is valid for one address. No new Python dependency.
- Firewall: mulebox prints a script for the operator instead of running anything as root;
  one nftables table for one port, leaving ufw, Docker and VPN clients alone.
- `mulebox-dashboard` no longer restarts on exit 2 (configuration), and a failed bind exits
  1 so that it retries. `/healthz` also returns `lan`.
- docs/phases.md: new M2.6 machines panel (next after M2.4), new M5.3 per-machine metrics.

## 0.7.1 - 2026-11-04 - patch
- docs/phases.md: parking lot ideas from the user: agent contract, installable skill, agent
  feedback through GitHub issues, project registration. No behaviour change.

## 0.7.0 - 2026-11-04 - minor
- Web dashboard (M2.1-M2.3, `local` part of M2.4): `mulebox dashboard open` on the laptop,
  service `mulebox-dashboard` on the coordinator machine. Queue, live log, history, CPU per
  core, memory, disk, Docker. Read-only and bound to 127.0.0.1; plain HTML and JS, no CDN.
  Contract: docs/interfaces-m2.md. New dependency: aiohttp.
- `common/status.py`: one status model for the terminal view and the dashboard.
- Found in real use and fixed before release: `ssh -L` joined a shared `ControlMaster` and
  exited, leaving a forward nobody held (the tunnel is now its own connection); a browser
  filter list blocked a script named `logview.js`, which blanked the page (renamed, and the
  page now says what to check if its scripts never run).
- README no longer claims LAN access, which is not built yet.

## 0.6.5 - 2026-11-04 - patch
- M3.3 done. A runner recovers from a hard kill by itself (GitHub drops the old session
  after ~3 min). Reboot drill passed with an agent job running and a CI job waiting; sudden
  power loss was not tested. Recovery times are in docs/interfaces-m3.md.

## 0.6.4 - 2026-11-03 - patch
- docs/phases.md: M3.1 and M3.2 done; M3.3 drill results (overlap, cancelled run, runner
  crash passed; GitHub session conflict after a hard kill and the reboot drill still open).
  Repository CI is now 16 s warm (was 47 s). M2 started on branch m2-dashboard.

## 0.6.3 - 2026-11-03 - patch
- Faster repository CI: tests run in parallel (`pytest-xdist`, `-n auto`; 23 s -> 5 s on
  the laptop), the venv is kept in the runner tool cache and rebuilt only when
  `pyproject.toml` changes. A parametrized protocol test now collects in a fixed order
  (it iterated a set, which xdist rejects).

## 0.6.2 - 2026-11-03 - patch
- Fixes from the first CI run on a mulebox runner (Linux, Python 3.12.3, the minimum):
  - `test_stream_early_stop_reaps_process` expected stderr closed; since 0.5.1 reap leaves
    a pipe to its still-waiting reader (another process held it on Linux). Test corrected.
  - GitHub does not tell hooks the job's result, so a released runner slot showed as
    "passed". Queue entries now carry `kind`; `mulebox queue` shows runner slots as
    `released` (the real result is on GitHub).

## 0.6.1 - 2026-11-03 - patch
- Repository CI (`.github/workflows/ci.yml`): the test suite on a mulebox runner by default,
  switchable with the `CI_RUNS_ON` repository variable. First real use of M3.

## 0.6.0 - 2026-11-03 - minor
- M3 GitHub runners, built in parallel on two branches:
  - Slot reservations: runner job-started/completed hooks reserve a slot pinned to the
    worker in the same FIFO queue as agent jobs (`reserve`, `acquire`, `release`,
    `runner_jobs`); the worker supervises runners and releases a crashed runner's slot
    after 60 s. Store schema 2 with an in-place migration.
  - Runner management: `mulebox runner register|unregister --repo owner/name` on the
    laptop (token from `gh`, sent on stdin), `mulebox runner add|list|remove` on the build
    machine (latest actions/runner release, checksum verified, `mulebox-runner@` user
    unit). The token never appears in argv or logs.
- `.mulebox.yml` `env:` for throwaway CI values; `${MULEBOX_JOB_ID}` / `${MULEBOX_JOB_SLUG}`
  and earlier entries expand, no shell. Store schema 3.
- docs/agents.md: a guide for coding agents (everyday use, setting a project up, moving
  GitHub Actions to mulebox runners); linked from the README.
- Shared download/verify code in `mulebox/common/download.py`.

## 0.5.3 - 2026-11-03 - patch
- docs/interfaces-m3.md: contract for GitHub runners (slot reservations through runner
  hooks, supervision, runner install from the laptop), so M3 can be built in parallel.
- `mulebox/runners/` package stubs wired into the CLI.

## 0.5.2 - 2026-11-03 - patch
- Client lease 120 s -> 300 s, and the client keeps reconnecting the live view for up to
  4 min (24 tries, 10 s apart): a real build machine on Wi-Fi dropped off for ~3 min, which
  would have cancelled a healthy job.
- After giving up on the live view, the client says the job keeps running and how to
  read its result (`WatchLost`), instead of the wrong "the job was not run".
- docs/phases.md: M1.6 done (real project passes, broken commit fails like locally); M1
  complete.

## 0.5.1 - 2026-11-03 - patch
- Fixes found by running M1.5 / M1.8 / M1.9 on a real build machine:
  - Ctrl-C took up to 2 minutes: closing an ssh pipe waited on a reader thread still
    blocked on it. `ssh.reap` no longer closes a pipe a live thread is reading.
  - A crashed worker's jobs stayed "running" until the 120 s worker lease ran out. The
    first claim after a worker start now carries `restarted: true` and the coordinator
    interrupts the jobs that worker still held (`recovery.release_worker`).
  - An ssh process killed by a signal counts as a lost connection (`SSHUnavailable`), so
    the watch stream reconnects instead of failing.
- docs/phases.md: M1.5, M1.8 and M1.9 done.

## 0.5.0 - 2026-11-03 - minor
- M1.4 coordinator (`mulebox/coordinator/`): SQLite store (WAL, `BEGIN IMMEDIATE`),
  atomic claim with cluster slots, idempotent submit, client and worker leases, restart
  recovery, upload staging with hash check and size cap, logs, `rpc` / `rpc-upload` /
  `rpc-download`, the watch stream, `coordinator serve`.
- M1.5 worker (`mulebox/worker/`): claim loop, safe workspace extraction plus a local git
  commit, systemd and subprocess executors, log tailing through the redactor, heartbeats
  and cancel, recovery of orphan units and job folders, node/pnpm toolchain install.
- M1.6 / M1.7 client (`mulebox/client/`): snapshot with built-in secret excludes, upload,
  submit, live log, exit codes like a local run, Ctrl-C cancel, stale warning, `queue`
  (with a live view), `logs`, `cancel`.
- M1.8 install (`install/`, `tools/deploy.sh`, docs/install.md): build-machine install as
  two systemd user services; never deletes, never uses sudo.
- Integration: worker local link wired to the coordinator; one shared line cap
  (`protocol.MAX_LINE_BYTES`); ssh helpers made public instead of reached into; worker
  heartbeat 3 s so a cancel lands in seconds; finished status replies carry the duration;
  `.envrc` and `.netrc` added to the secret excludes.
- Verified end to end on one machine with a fake ssh: pass, fail (same exit code),
  `mulebox cancel`, Ctrl-C (exit 130 in 1 s, no processes or folders left).
- docs/interfaces-m1.md: decisions made during the build.

## 0.4.1 - 2026-11-03 - patch
- docs/interfaces-m1.md: contract for the coordinator, worker, client and install script
  (M1.4 - M1.8), so they can be built in parallel. M1 simplifications recorded there (full
  snapshot instead of a build-machine clone, `rpc` opens SQLite directly).
- Protocol: message types `queue`, `queue_ok`, `logs`, `watch`.
- Package stubs `client/`, `coordinator/`, `worker/` with `commands.register`; the CLI
  dispatches to each subcommand's handler.

## 0.4.0 - 2026-11-03 - minor
- M1.3 `mulebox/common/safepath.py` (+ `roots.py`, `mounts.py`): the only code that
  deletes. Roots validated once (no `/`, home, system folders or overlaps; device and inode
  recorded). Deletion and creation anchored on directory descriptors with `O_NOFOLLOW`;
  the walk never follows symlinks, never leaves the root's mount (Linux mount ids from
  `/proc/self/mountinfo` and fdinfo, macOS `st_dev` + `ismount`), refuses mount points.
  Permission failures raise `RemovalDenied`; no escalation in this module.
- Tests cover symlink swaps mid-check and mid-walk, simulated mounts, prefix lookalikes,
  fd leaks; also run on Linux in a container.
- Known gaps: a directory renamed out of the root by someone with write access mid-delete;
  same-device mounts undetectable on macOS; real mounts only simulated in tests.
- README: rerun the editable install after a VERSION bump.

## 0.3.0 - 2026-11-03 - minor
- M1.2 shared modules in `mulebox/common/`, built in parallel to docs/interfaces.md:
  - `ids.py`: prefixed ULIDs (`job-...`), validation, timestamps.
  - `log.py`: idempotent setup of the `mulebox` logger, text or JSON lines.
  - `config.py` + `config_reader.py`: `.mulebox.yml`, `client.toml`, `node.toml`, strict
    validation (unknown keys, ranges, CIDR, ssh targets); errors name file and field.
  - `protocol.py`: versioned JSON-line messages, required body fields per type, job state
    machine (no self-transitions; finished is terminal).
  - `ssh.py`: argv-only subprocess, `--` before the `shlex.join` remote command, exit 255
    as `SSHUnavailable`, `RemoteError` / `RemoteTimeout`, streaming without deadlocks.
  - `redact.py`: known secrets and token patterns blanked; `StreamRedactor` catches secrets
    split across chunks.
- PyYAML 6.0.3 pinned as the first runtime dependency.
- docs/interfaces.md: additions found while building (see "Decisions made in M1.2").
- Known gaps: duplicate YAML keys are not detected; `decode` has no line-size cap (the
  reader must cap it); `RemoteError.stderr` is raw and must be redacted by callers.

## 0.2.1 - 2026-11-03 - patch
- docs/interfaces.md: the API contract for the shared modules (ids, log, config, protocol,
  ssh, redact, safepath), so they can be built in parallel.
- `mulebox/common/` package with the base `MuleboxError`.

## 0.2.0 - 2026-11-03 - minor
- M1.1 package skeleton: `pyproject.toml` (Python 3.12+, setuptools 84.2.1, version read
  from VERSION), `mulebox` CLI entry point with `--version` / `version`, pytest 9.2.0 as the
  pinned dev dependency, tests for the CLI and version source.
- File-size rule enforced in code: `tools/check_line_counts.py` warns above 300 lines and
  fails at 500; the test suite runs it on the whole repository.
- README: development section (venv, install, tests).

## 0.1.0 - 2026-11-03 - minor
- Project created from the design work in a private setup repo: README, design, roadmap
  (docs/phases.md), versioning and project-log rules, agent rules.
- Design reviewed by an external model (core queue, dashboard, multiple machines); the
  adopted changes are part of docs/design.md.
- Groundwork measured on a real setup (M4 Pro laptop vs a 2014 4-core i7 on Wi-Fi): the old
  machine ran two real CI suites 1.8x and 3.5x slower than the laptop, but 2-3x faster than
  GitHub-hosted runners, with the laptop left idle. Basis for "offload, then queue".
