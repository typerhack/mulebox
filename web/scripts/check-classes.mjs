// Fails when a value is typed into a class name or a stylesheet instead of coming from the
// design system's tokens (AGENTS.md rule 10, docs/design-system.md). Run by `npm run lint`.
//
// In code (src/**/*.ts, *.tsx):
//   - Tailwind arbitrary values and variants: `w-[10px]`, `[&>*]:p-2`, `bg-(--x)`;
//   - bare-number utilities that would bypass a token: `duration-150`, `delay-75`,
//     `text-[..]`, `rounded-[..]`;
//   - a colour literal (`#1c9c8f`, `rgb(...)`, `hsl(...)`).
// In stylesheets other than theme.css (the one file that maps tokens to names):
//   - a colour literal, and any px length other than the 1px and 2px of hairlines and the
//     accent line.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(import.meta.dirname, "..");
const COLOUR = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab)\(/;
const CODE_RULES = [
  [/[a-z0-9]-\[[^\]]*\]/, "arbitrary value in a class name"],
  [/(?:^|[\s"'`])\[[^\]\s"'`]+\]:[a-z@*[]/, "arbitrary variant in a class name"],
  [/[a-z]-\(--[^)]*\)/, "CSS variable typed into a class name"],
  [/\b(?:duration|delay)-\d/, "a duration typed into a class name"],
  [COLOUR, "colour literal"],
];
const CSS_RULES = [
  [COLOUR, "colour literal"],
  [/(?<![\w.-])(?!(?:1|2)px\b)\d*\.?\d+px\b/, "a px length that is not a token"],
];
const CSS_FREE = new Set(["src/styles/theme.css"]);

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

export function problems(path, text) {
  const name = relative(ROOT, path);
  const css = name.endsWith(".css");
  if (css && CSS_FREE.has(name)) return [];
  if (!css && !/\.tsx?$/.test(name)) return [];
  const rules = css ? CSS_RULES : CODE_RULES;
  const found = [];
  text.split("\n").forEach((line, index) => {
    const code = line.replace(/\/\/.*$/, "").replace(/\/\*.*?\*\//g, "");
    for (const [pattern, what] of rules) {
      if (pattern.test(code)) found.push(`${name}:${index + 1}: ${what}: ${line.trim().slice(0, 100)}`);
    }
  });
  return found;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const found = files(join(ROOT, "src")).flatMap((path) => problems(path, readFileSync(path, "utf8")));
  for (const line of found) console.error(line);
  if (found.length) {
    console.error(`\n${found.length} value(s) typed in. Use a token, or name the size once in src/styles/theme.css.`);
    process.exit(1);
  }
  console.log("class names and stylesheets use tokens only");
}
