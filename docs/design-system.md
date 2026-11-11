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
| Meters and graph | `--meter-track`, `--meter-fill`, `--graph-line` | resource meters and the CPU line |
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

## Space and layout

- A 4px base, `--space-1` to `--space-8`. 12px inside panels and between them (`--app-gap`).
- Page sides: `--gutter`.
- Layouts work from 390 px (no sideways scroll) to 1440x900.
- A row never squeezes text into a column narrower than its words. If it does not fit, the row
  wraps or the fact moves to the job's page.

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
- No shadows, except `--shadow-2` under a menu, the one thing that floats above the page.

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
  `chevrons-up`, `chevron-up`, `chevron-down`, `chevrons-down`.
- On cards the icon stands alone and the word is its tooltip. In tables and on a job's page the
  icon comes with its word.

## Components

Drawn in the specimen, in both themes:

- Buttons: primary (accent, at most one per view), secondary, ghost, danger (outlined, filled on
  hover), icon button. Heights 32px, icon buttons 28 to 30px with a pointer, 36px on touch
  screens or under 520px.
- Tabs with counts: a 2px accent line under the selected tab.
- Job state icons and the frozen, paused and boosted marks.
- Meter (6px high), live line graph, machine row with slot boxes.
- Running job card with its three-dots menu. Menu items have an icon, a bold name and one plain
  hint.
- Waiting row: position, name, branch, time waited, the four move arrows as one group, three dots.
- Warning strip (amber) and danger strip (red), each with its fix.
- Tooltip, empty state.

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

Found in a review of the proposal (2026-11-10), to settle in the first React components (M14.10):

- Controls are 28 to 32px with a pointer and 36px on touch screens or under 520px
  (`--spacing-ctl-*` in web/src/styles/theme.css). Measured on the deployed dashboard
  (2026-11-11): 28 to 34px with a pointer, which meets WCAG 2.2 AA (24px); 36px on touch is
  under the 44px of Apple's and the 48px of Google's guidance. Whether to raise it is the
  user's call.

Settled in the React dashboard (M14.10):

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

