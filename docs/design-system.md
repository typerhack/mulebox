# Design system: Gauge

The rules every mulebox screen follows, so the dashboard reads as one product. Chosen by the user
on 2026-11-10 from three proposals (the other two were Stable and Signal). Any UI work starts
here.

- Token values: [design-system/tokens.css](design-system/tokens.css), the one source. Code
  imports this file and never copies its values; this page names the tokens, it does not
  repeat them.
- Picture: [design-system/specimen.html](design-system/specimen.html), every component in both
  themes. Open it in a browser. Where it and tokens.css differ, tokens.css wins.

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
| Chart series | `--chart-1` to `--chart-6` | charts with more than one series, in this fixed order |

- Status color sits on the icon only. The word beside it stays in `--text-1`.
- Frozen, paused and boosted are marks on a job, not results: they are drawn in ink
  (`--text-1`), never in a status color.
- A meter turns `--status-warning` from 80% and `--status-danger` from 92%, and gets the
  warning or alert icon beside its number.
- Chart series take `--chart-1` onwards in order, never cycled; a seventh series folds into
  Other. Three light values are under 3:1 on a white panel, so every series also has a label or
  a legend with its number. The single CPU line uses the accent.
- Teal and the passed green are close for some color vision. A state is therefore always an
  icon with its own shape, never a colored dot.

Contrast: every text and control pair passes WCAG AA in both themes (64 of 64 pairs, checked
from the token values; the table is in the specimen). Panel hairlines sit near 1.4:1 on purpose,
as decoration; anything you can press uses `--border-strong`.

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

- Rows and cards use 6px and 10px gaps that are not on the scale. Either they become tokens or
  they move to 8px and 12px.
- Controls are 28 to 32px with a pointer and 36px on touch screens, smaller than the common 44px.
  Check them in real use before keeping them.
- Not drawn yet: a running job that is also frozen or boosted, the Resume and Unboost menu
  items, the stage waterfall and the live log as components.
