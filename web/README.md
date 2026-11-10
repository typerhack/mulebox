# The dashboard's front end

React 19, Vite, TypeScript and Tailwind CSS v4, following the design system
([../docs/design-system.md](../docs/design-system.md)). What it shows and which routes it reads:
[../docs/interfaces-m2.md](../docs/interfaces-m2.md).

## Work on it

Node 22 and npm.

```sh
cd web
npm ci
npm run dev          # http://localhost:5173/app/ with made-up data
```

`npm run dev` alone serves a stand-in API (`dev/mock.ts`, `dev/fixtures.ts`): a queue with every
kind of row, and controls that change it, so menus, arrows, Pause and Cancel can be tried without
touching a real queue. `MULEBOX_MOCK_MACHINES=20 npm run dev` gives twenty machines.

To see real data, point it at a dashboard; requests go through Vite's proxy:

```sh
MULEBOX_DASHBOARD=http://192.168.1.50:8090 npm run dev
```

Reading works. The dashboard refuses changes from the dev server's origin, as it would from any
page that is not its own, so try the controls against the stand-in.

## Checks

```sh
npm run lint         # eslint, then scripts/check-classes.mjs
npm run typecheck
npm test             # vitest
npm run build        # into ../mulebox/dashboard/app/, which the Python package ships
```

The repository's CI runs the same four (`web` job).

## Rules

- **Tokens only.** `src/styles/theme.css` maps
  [../docs/design-system/tokens.css](../docs/design-system/tokens.css) into Tailwind and leaves
  Tailwind's own palette and scales out, so `gap-3` is `--space-3` and `text-ink-2` is
  `--text-2`. tokens.css is imported by path and never copied. `scripts/check-classes.mjs` fails
  on an arbitrary value (`w-[10px]`), a duration or a colour typed into code, and a colour or
  px length in a stylesheet other than theme.css. A size the design system states in words but
  has no token for is named once, in theme.css, derived from a token.
- **The page's security policy** allows scripts, styles, fonts and images from its own origin
  only, and no inline script or style. React sets styles through the DOM, which is allowed.
  Do not add a library that injects a `<style>` element (Radix's Select and ScrollArea do, and
  its modal layers lock scrolling that way: menus here are `modal={false}`).
- **Small modules**, as in the rest of the repository: under about 300 lines, one job each.
  `src/lib/` holds what needs no React and has the tests; `src/ui/` the design system's
  components; `src/features/` one folder per view; `src/state/` the live data.
- **No state library.** The event stream (`/api/events`) fills small stores (`src/lib/store.ts`)
  that components read with `useSyncExternalStore`.
- Icons are Lucide, outline. An icon that stands alone has a tooltip and an accessible name.

## How it is served

`npm run build` writes static files to `mulebox/dashboard/app/` (not in git). The dashboard
serves them at `/` and `/app/` when they exist, and keeps the classic page at `/classic/`
(`mulebox/dashboard/pages.py`). `mulebox setup` runs the build before it makes the wheel it
sends, so a build machine needs no Node.
