# Design system: Gauge

The rules every mulebox screen follows, so the dashboard reads as one product. Chosen by the user
on 2026-11-10 from three proposals (the other two were Stable and Signal). Any UI work starts
here.

- Token values: [design-system/tokens.css](design-system/tokens.css), the one source. Code
  imports this file and never copies its values; this page names the tokens, it does not
  repeat them.
- Picture: [design-system/specimen.html](design-system/specimen.html), every component in both
  themes. Open it in a browser. Where it and tokens.css differ, tokens.css wins.
- The dashboard in this system: [design-system/dashboard-mockup.html](design-system/dashboard-mockup.html),
  the layout the user picked ("Monitor on top", 2026-11-10), with its Queue, job and CI job pages,
  a 390 px view and both meter styles. It is the picture M14.1 and M14.10 build.

## The idea

A bench instrument: hairlines, small corners, thin meters and tight type, with the teal mulebox
already uses for what you can act on. A live monitor earns trust by being exact. Gauge fits more
on a screen and stays readable by ordering things, not by decorating them. Its risk is density:
it is only as calm as the discipline about what a row shows (see Rules).

Home theme: dark. The dashboard still offers system, light and dark, with system as the default.

## Color

Every color is a role. A role is used only for what its name says.

| Role | Tokens | Used for |
|---|---|---|
| Surfaces | `--surface-0` to `--surface-3` | page, panel, inset or card, hover and pressed |
| Text | `--text-1`, `--text-2`, `--text-3` | main text, secondary text, muted text |
| Lines | `--border`, `--border-strong` | hairlines (decoration); outlines of anything you can press |
| Accent | `--accent`, `--accent-hover`, `--accent-ink`, `--focus` | the primary action, the selected tab, focus, meters |
| Status | `--status-running`, `-queued`, `-passed`, `-failed`, `-cancelled`, `-warning`, `-danger`, `--on-danger` | job results and alerts, on the icon only |
| Strip tints | `--status-warning-soft`, `--status-failed-soft` | the background of the warning and danger strips, nothing else |
| Meters and graph | `--meter-track`, `--meter-fill`, `--meter-fill-soft`, `--graph-line` | resource meters and the CPU line; the soft fill only for the second part of a usage bar (Components) |
| Chart series | `--chart-1` to `--chart-6` | the marks and legend swatches of charts with more than one series, in this fixed order: teal, ochre, indigo, rose, slate, light blue |
| Load ramp | `--ramp-lo`, `--ramp-mid`, `--ramp-hi` | the Rainbow meter style only (below) |

- Status color sits on the icon only. The word beside it stays in `--text-1`.
- Frozen, paused and boosted are marks on a job, not results: they are drawn in ink
  (`--text-1`), never in a status color.
- A meter turns `--status-warning` from 80% and `--status-danger` from 92%, and gets the
  warning or alert icon beside its number.
- Chart series take `--chart-1` onwards in order, never cycled; a seventh series folds into
  Other. The palette is muted to the level of the rest of the page (the user's pick on
  2026-11-10, over the brighter reference palette): series 1 is the teal of meters and of every
  single bar, so mulebox jobs are the same teal in a split bar and in a breakdown; series 2, on
  the Statistics page GitHub Actions, is a dull ochre.
- A series color is for chart marks and legend swatches only, never for an icon or text: the
  ochre is close to the warning amber, and a label in it would read as a warning. Labels,
  values and legends stay in the text colors.
- In the light theme series 4 and 6 are under 3:1 on a white panel, and the ochre is under 3:1
  on a grey card (`--surface-2`), so every series also has a label or a legend with its number.
  Series 1 and 2 are told apart by all three kinds of color vision in both themes. The single
  CPU line uses the accent.
- Teal and the passed green are close for some color vision. A state is therefore always an
  icon with its own shape, never a colored dot.

Contrast: every text and control pair passes WCAG AA in both themes (64 of 64 pairs, checked
from the token values; the table is in the specimen). Panel hairlines sit near 1.4:1 on purpose,
as decoration; anything you can press uses `--border-strong`.

## More than one machine

Decided by the user on 2026-11-10 from three variants ("B, click a row"; a dropdown and a strip of
machine names were the others, the strip rejected):

- Machines are named by their worker name (`node.toml`), the same for everyone; the dashboard's
  own machine carries a house mark and "Dashboard host".
- CPU, Memory and Disk show the host by default. Clicking a machine in the Machines box shows that
  machine in all three, its name in each panel's header and an accent line on its row; "Back to
  host" in the CPU header returns. An offline machine keeps the panels' shape and says when it
  was last seen.
- The top row never changes size with the number of machines or the pick. With two machines the
  Machines box is as before; with more, one line per machine scrolling inside the box, and a link
  to the Machines page at its foot.
- The Jobs box gives a lane only to a machine that runs or waits for something; the rest are one
  line ("Nothing running on 14 machines").
- A lane that has both running and waiting jobs is two halves: the running cards on the left
  under "Running", the line on the right under "Waiting in line", a hairline between them. Two
  cards sit side by side in the running half when each can be 280px wide (4 slots on a wide
  screen), else they stack. A lane with only one of the two has no headings and takes the whole
  width, as do the shared "Next free machine" list and the stuck jobs. Under 760px of Jobs box
  the halves stack, headings kept. A waiting row folds by the width of its own list: time,
  arrows and three dots drop under the name when the list is under 640px.
- A line of more than 6 shows its first 5 and "Show all waiting (N)", which opens the rest in
  place ("Show the first 5" closes it). Rows keep their real positions either way, and the
  lane's note counts them all.
- A Machines page beside Queue lists every machine with its state, readings, slots, offers,
  version and last seen, sortable, with its pause button.
- Usually 4 or 5 machines; the layout holds at 20.

## Meter styles

Two styles for load: resource meters (CPU per core, memory, disk, a machine's CPU and memory, a
card's cores) and the CPU graph. Each viewer picks Auto, Gauge or Rainbow; the choice is
remembered per browser, like the theme, with a switch beside the theme switch. Auto is the
default: Rainbow in the light theme, Gauge in the dark one, following the theme as it changes
(the system's too). Decided by the user on 2026-11-10 after seeing both: Rainbow looked best to
them in light, Gauge in dark, and they want the viewer to choose.

- **Gauge**: one solid fill, `--meter-fill`, on a `--meter-track`; the graph in `--graph-line`
  with a faint fill. A meter turns warning and danger at the thresholds above.
- **Rainbow**: the load ramp of the dashboard before Gauge. Meters are segmented (5px blocks,
  2px gaps) and coloured by position from `--ramp-lo` through `--ramp-mid` (at 62%) to
  `--ramp-hi`, so how full a meter is shows in its colour; the graph's line and area take the
  same ramp from bottom to top, the area at about 40% opacity.
- Only load uses the ramp. Job states, strips, buttons and everything else follow the rest of
  this page in both styles; the ramp is the one allowed exception to "status colour only for
  status", and only for load.

## Type

- Geist for text, Geist Mono for what is typed or machine-made: logs, branch names, commands,
  positions in line. Both are open (OFL) and bundled with the app, never loaded from the web.
- Three weights only: 400, 500, 600.
- Scale: `--text-xs` (branches, counts) up to `--text-display`. Base is `--text-base`. Nothing
  smaller than `--text-xs`.
- Numbers line up: tabular figures, aligned right, never wrapped.
- Sizes and rates in decimal SI units, as package managers and download tools print them: B, KB,
  MB, GB, TB, 1000-based, and KB/s, MB/s, never KiB or MiB. Whole bytes under 1 KB, one decimal in
  every unit above (`906.4 MB`, `41.0 MB`, `614.0 KB/s`). One formatter each side: `bytes` and
  `rate` in web/src/lib/format.ts, `mulebox/common/units.py` for the terminal and the logs.
  Percentages stay as they are.

## Space and layout

- A 4px base, `--space-1` to `--space-8`. 12px inside panels and between them (`--app-gap`).
- Page sides: `--gutter`.
- Layouts work from 390 px (no sideways scroll) to 1440x900.
- A row never squeezes text into a column narrower than its words. If it does not fit, the row
  wraps or the fact moves to the job's page.
- The header's views (six since Usage, 2026-11-25) stay on one line while they fit. Under 760px
  they are a row of their own under the name, and wrap to a second line there when they do not
  fit: no entry shrinks, loses its word or scrolls sideways, and each keeps its 44px. On a phone (520px or less)
  their icons go, the gap between them is `--space-2`, and the Storage count is a dot (its
  number in its label and title), so the six fit on one line at 390px; wrapping stays the fallback
  for a narrower screen.

## Corners

One radius per level, stepped by size:

| Token | Used on |
|---|---|
| `--radius-s` | menu items, counts, tooltips (meters use 3px, half their height) |
| `--radius-m` | buttons, icon buttons, cards, strips |
| `--radius-l` | panels and menus |
| `--radius-full` | nothing round is planned yet; kept for a pill if one is ever needed |

## Lines and elevation

- Hairlines separate: 1px `--border` around panels and between rows, 1px `--border-strong`
  around anything you can press. Cards are one tone off the panel (`--surface-2`) with a hairline.
- No shadows, except `--shadow-2` under what floats above the page: a menu, a panel opened from a
  button, and a window (the user's agreement, 2026-11-13).

## Motion

- `--dur-fast` for hover and press, `--dur-base` for a meter moving to a new value and a menu
  opening.
- Only two things move by themselves: the running icon turns, and meters glide. With reduced
  motion the icon stands still and values change at once. Nothing fades in on load.

## Icons

- Lucide, outline only, never filled. Stroke 1.5 at 16px; 1.75 on status icons, so a state
  outweighs a decoration. Sizes 14, 16, 18 and 20.
- An icon alone always has a tooltip and an accessible name.
- Job states: running `loader-circle`, queued `clock`, passed `circle-check`, failed `circle-x`,
  cancelled `ban`. Marks: frozen `snowflake`, paused `pause`, boosted `zap`. Alerts: warning
  `triangle-alert`, danger `octagon-alert`. Menus: `ellipsis` (three dots). Move in line:
  `chevrons-up`, `chevron-up`, `chevron-down`, `chevrons-down`. Copy: `copy`, then `check` for a
  moment once copied. Usage: cores `cpu`, memory `memory-stick`, a gap in the measurements
  `circle-dashed`, a list sorted heaviest first `arrow-down-wide-narrow`.
- On cards the icon stands alone and the word is its tooltip. In tables and on a job's page the
  icon comes with its word.

## Components

Drawn in the specimen, in both themes:

- Buttons: primary (accent, at most one per view), secondary, ghost, danger (outlined, filled on
  hover), icon button. Heights 32px, icon buttons 28 to 30px with a pointer, 44px on touch
  screens or under 520px (the user's choice, 2026-11-11, from 36px).
- Tabs with counts: a 2px accent line under the selected tab.
- Job state icons and the frozen, paused and boosted marks.
- Meter (6px high), live line graph, machine row with slot boxes.
- Running job card with its three-dots menu. Menu items have an icon, a bold name and one plain
  hint.
- Waiting row: position, name, branch, time waited, the four move arrows as one group, three dots.
- Download meter on a running card (the user's pick of three, 2026-11-13;
  [design-system/download-progress-mockup.html](design-system/download-progress-mockup.html),
  option A): a "Down" row under Cores, only while the job downloads. A meter that fills when the
  total is known, a dashed open track in `--border-strong` when not, and below it "Downloading"
  with what, and the speed as a fact of its own. When no byte has moved for a while the fill
  and a warning icon take `--status-warning` and the line says "No bytes for 75 s"; the open
  track stays as it is. It is not load: one solid fill in both meter styles, and no warning at
  80% (`web/src/features/jobs/DownloadMeter.tsx`).
- Warning strip (amber) and danger strip (red), each with its fix.
- A running job's verdict (the user's pick of three, 2026-11-15;
  [design-system/stuck/](design-system/stuck/index.html), option B; design.md, A job that looks
  stuck): one line across the foot of its card, above a hairline, with the verdict's icon in its
  level's colour, its name in words and one figure: `snail` in `--status-warning` for "Slow
  download" with the rate, `hourglass` in `--status-queued` for "Waiting on purpose",
  `text-cursor-input` and `octagon-alert` in `--status-danger` for "Asks for input" and "Looks
  stuck", each with how long the job has been quiet, counting on. A working job shows nothing,
  and the state icon keeps turning, as the job still runs. The line is a button (28px, 44px on
  touch): pressed, it opens in place to the coordinator's sentence, "Open its log" and, where
  the page has controls, the two-step "Cancel job". On the job's page the same verdict is a
  strip under the header, in the danger, warning or plain colours of its level, with "Go to its
  last line" (`web/src/features/jobs/LooksLine.tsx`, `web/src/features/job/LooksNote.tsx`).
- The tests a finished job ran (the user's pick of three, 2026-11-15;
  [design-system/tests/](design-system/tests/index.html), option B; design.md, Proof that tests
  ran): on its row the count is a quiet number with `list-checks` in `--text-2` ("3675 tests",
  "+12" when the suite grew). Only a count that failed the job or was let through adds a line
  in words under the job's name, the colour on its icon alone: `list-minus` (fewer) and `list-x`
  (none) in `--status-failed`, `list-minus` in `--status-warning` for a drop the agent allowed,
  with its reason in its own words. On the job's page the same is a danger or warning strip
  under the header with its fix, and a Tests panel under Stages with each runner beside the
  last pass; the runners' summary lines in the log are underlined
  (`web/src/features/jobs/TestsBits.tsx`, `web/src/features/job/TestsNote.tsx`, `TestsPanel.tsx`).
- Usage bars (the user's picks, 2026-11-25, of [design-system/usage/](design-system/usage/index.html):
  the Usage page of option A, one run as in option B; design.md, Job usage). A usage bar is 12px
  high and its whole track is the node, ruled in units (a core, or a few GB), so the bars of one
  node share one scale. The solid part (`--meter-fill`) ends at the usual peak, the soft part
  (`--meter-fill-soft`) at the highest, and the numbers are always written under it. It is a
  measurement, not load: one solid fill in both meter styles, like the download meter, and never
  a warning colour, however full. A gap is said in words after `circle-dashed`, never drawn as
  zero. On a job's page there is no bar: each peak is one line under the stage it happened in,
  led by `cpu` or `memory-stick` in `--text-1`, and the average is the panel's last line, above
  a hairline (`web/src/features/usage/`, `web/src/features/job/UsageLines.tsx`).
- The ink tick: a 2px line in `--text-1` across a bar, always a value to hold the bar against,
  never the bar's own. On a stage it is where the stage usually ends, on a usage bar the size
  that fits every run, on a running job's Cores meter its peak so far, on the disk ruler the
  reserve. What it means there is said in the key beside the bar.
- Tooltip, empty state.
- Tables: the first and the last cell of a row keep `--space-3` from the row's edges, header
  included, so a shaded row never has its name or its buttons on its border (the user's ask,
  2026-11-13).
- Settings controls (the user's agreement, 2026-11-13, for node settings and queue order): a
  switch (on in `--accent`, a visible label beside it, 44px touch target), a segmented choice (one
  of a few, such as High, Normal, Low; arrow keys move between parts), and a number stepper (minus, value in mono, plus; typed values allowed, out-of-range
  refused with the range said).
- The segmented choice is radio marks (the user's pick, 2026-11-13, option C of
  [design-system/segmented-options.html](design-system/segmented-options.html), after the first
  one, an outlined group with an accent line under the chosen part: "especially the underline
  border, it's pretty bad"). No box and no line: a ring before each word (`--border-strong`), the
  chosen ring filled in `--accent` with its word heavier and in `--text-1`, so the choice is
  never colour alone. A part is as wide chosen as not. Hover shades the part (`--surface-3`) and
  darkens its ring; keyboard focus is the page's own ring around the part, a different mark from
  the chosen one. Off or read only, nothing is in the accent: the chosen ring is filled in
  `--text-3`. Parts are 32px high, 28px in dense rows (`small`), 44px on touch or under 520px,
  and wrap under their row's name when the row is narrow, never past its edge. Used for a node's
  Priority, the levels of the queue order and the period of the Statistics table. In code:
  `web/src/ui/Segmented.tsx`, `.seg` in `web/src/styles/components.css`.
- Floating surfaces: a panel opened from a button (anchored to it) and a window (centred, page
  dimmed behind). Both `--surface` with a hairline and `--shadow-2`, dialog semantics, Escape and a
  close button, focus moves in on open and back to the opener on close. A change is "Unsaved" until
  Save, and "Pending" only after Save while a node has yet to take it.
  Their tokens: `--scrim` dims the page under a window (the page colour, part see-through, so it
  follows the theme), and `--window-width` is the widest a window gets.
  In code: `web/src/ui/Stepper.tsx`, `Segmented.tsx` and `Window.tsx`; the page under a window
  cannot be reached while it is open. First used by the
  node settings window (`web/src/features/machines/NodeSettings.tsx`), whose body is the page's
  colour (`--surface-0`) holding panels like the top row's (the user's ask, 2026-11-13, after the
  first table "hurt the eyes"): a panel per setting, with its name and icon, one line on what it
  means, then Suggested, Yours and Runs with as rows with the name on the left and the value on
  the right, a hairline between rows and the reason on a line under its row; beside them a panel
  of what the node reports, as the Disk panel lists its facts. Under them on the Jobs tab, "Room
  for you" (1.39, option A of design-system/owner-room/, the user's pick): one full-width panel
  with two parts, cores and memory kept for the owner, each with the same three rows and a line on
  what jobs with a size share. Both tabs set their panels two to a
  row, one column under 640px of their own width; the panels of a row are as tall as each other
  and their rows (the meaning, Suggested, Yours, Runs with) line up across the row, each panel's
  rows taken from the grid it sits in (`Panel` with `subgrid`, `.setting-panels`), with the
  controls on the panel's right edge. While a save is on its way its
  controls take no edit, and an open window reads its node again every few seconds, keeping
  what the viewer has changed and not saved.
  A panel is `--pop-width` (380px) wide or as wide as its host, whichever is less, and at most
  `--pop-height` (640px) tall: its head and foot stay and its body scrolls. It hangs under the
  button that opened it (CSS anchor positioning), and at its host's top right where that button
  has gone or the browser cannot anchor; the panel itself stays open, so what is typed in it is
  kept. In code:
  `web/src/ui/Float.tsx` (the panel), `Switch.tsx`, and the same `Segmented.tsx` (`small`, 28px
  and inline, for dense rows) and `Stepper.tsx` (`step`) as the window.
- Queue order (the user's pick, 2026-11-13, option A of
  [design-system/queue-order-mockup.html](design-system/queue-order-mockup.html)): an Order button
  on a waiting line's heading opens the rules in a panel. The rules are a numbered ladder,
  strongest first, because their order is the fact to show; a rule that is always on carries a
  lock. A waiting row says why it stands where it does on a second line, in `--text-2`, led by the
  rule's icon: by hand `hand`, a project's level `flag` (a low one `arrow-down`), a branch
  `git-branch`, a workflow or GitHub runs `workflow`, time waited `hourglass`, fair turns `repeat`,
  shortest first `timer`, arrival `clock`. The Order button itself is `list-ordered`.
- Storage (the user's picks, 2026-11-14, of [design-system/storage/](design-system/storage/index.html):
  view A with C's line in the Disk panel and B's list behind a button, settings A with C's one
  line, notices A for the warning and B for the suggestion). The disk ruler: one bar 20px high for
  a whole disk, what mulebox holds in `--chart-1` to `--chart-5` by kind, everything else in
  `--surface-3`, free space empty, and the reserve hatched at the far end behind a 2px line in
  `--text-1` (`--status-danger` once the used part reaches it); what a removal would free is the
  same hatch outlined in `--status-passed`. Its numbers are always in words above it and in its
  legend. A storage row has three icon buttons, always in this order: `copy` the path, `pin` to
  keep (pressed and in `--accent` when kept), `trash-2` to clean; a clean opens a list of what
  goes under the row, and only its danger button removes. Fates carry an icon and words: `flag`
  latest, `pin` kept, `clock` stays, `timer` goes soon, `loader-circle` in use, `lightbulb` in
  `--status-warning` for a suggestion. A count on a header entry is a filled pill in `--text-1`.
- A line longer than its box, such as a GitHub step on a job card (the user's ask, 2026-11-12):
  cut with an ellipsis, the whole text in its tooltip, and a small quiet copy button beside it,
  in `--ink-3` until hovered (`web/src/ui/Copy.tsx`). Over plain HTTP, where browsers give a
  page no clipboard API, it copies through a hidden text field.
- The CPU box's two views (the user's idea, 2026-11-11), switched by a small icon button beside its
  note and remembered per browser: details, a meter per core, the default and unchanged; compact,
  an All meter, the busiest cores by number (six with four to a row, four on narrower screens,
  kept steady until another is 10 points busier) and one line for the rest with their average and
  highest. The switch shows only when compact would hide a core. Neither view scrolls.

## Rules

Do:
- Separate with hairlines and one tone step.
- Put status color on the icon only.
- Keep teal for what you can act on and for meters.
- Use mono for what is typed or machine-made.
- Let a panel show less. If a row needs a fourth fact, it goes to the job's page.

Do not:
- No tinted backgrounds for states, and no colored card borders except the strips.
- No text under `--text-xs`, and no facts squeezed into narrow columns.
- No filled icons, no dots standing in for states, no control drawn in `--border` alone.
- No shadows on panels or cards.
- No second accent. If something needs to shout, it is a status.
- No color, size, radius or duration typed into a component: only tokens.

## Open before building

Found in a review of the proposal (2026-11-10), to settle in the first React components (M14.10).
Nothing is open.

Settled in the React dashboard (M14.10):

- Controls are 28 to 32px with a pointer (measured 28 to 34px on the deployed dashboard,
  2026-11-11, which meets WCAG 2.2 AA's 24px) and 44px on touch screens or under 520px, as
  Apple's guidance asks; the user raised it from 36px on 2026-11-11.
- Gaps are on the scale only. The 6px and 10px gaps of the proposal became 4, 8 and 12px
  (`--space-1` to `--space-3`): 4px inside a line of facts, 8px between rows and cards, 12px
  inside a card and between a row's columns.
- A running job that is frozen or boosted keeps its card and gets an outline snowflake or bolt
  beside its three dots, with the word as tooltip; its menu then offers Resume or End boost
  (web/src/lib/menu.ts). Seen on agent jobs and on a GitHub run's card in real Edge.
- The stage waterfall and the live log are components of the job page
  (web/src/features/job/Waterfall.tsx, LogPanel.tsx, CiSteps.tsx for a GitHub run).
- The meter style switch is an icon button in the header, left of the theme switch, and steps
  through Auto, Gauge and Rainbow with the icons `contrast`, `gauge` and `rainbow`; its tooltip
  names the current style and the next one.

