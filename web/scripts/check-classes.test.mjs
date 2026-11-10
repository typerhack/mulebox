// @vitest-environment node
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { problems } from "./check-classes.mjs";

const at = (name) => join(import.meta.dirname, "..", name);
const found = (name, text) => problems(at(name), text).map((line) => line.split(": ")[1]);

describe("check-classes", () => {
  it("refuses values typed into class names", () => {
    expect(found("src/a.tsx", '<i className="w-[10px]" />')).toEqual(["arbitrary value in a class name"]);
    expect(found("src/a.tsx", '<i className="[&>*]:p-2" />')).toEqual(["arbitrary variant in a class name"]);
    expect(found("src/a.tsx", '<i className="bg-(--mine)" />')).toEqual(["CSS variable typed into a class name"]);
    expect(found("src/a.tsx", '<i className="duration-150" />')).toEqual(["a duration typed into a class name"]);
    expect(found("src/a.tsx", 'const c = "#1c9c8f";')).toEqual(["colour literal"]);
  });

  it("lets token classes and plain code through", () => {
    expect(found("src/a.tsx", '<i className="touch:h-ctl-touch bg-surface-2 p-3" />')).toEqual([]);
    expect(found("src/a.ts", "const a = list[0]; const b = { ...c, [key]: value }; go(`#/job/${id}`);")).toEqual([]);
  });

  it("refuses colours and px lengths in stylesheets, but not in the theme", () => {
    expect(found("src/styles/x.css", ".a { color: #fff; }")).toEqual(["colour literal"]);
    expect(found("src/styles/x.css", ".a { padding: 10px; }")).toEqual(["a px length that is not a token"]);
    expect(found("src/styles/x.css", ".a { border: 1px solid var(--border); width: 2px; }")).toEqual([]);
    expect(found("src/styles/theme.css", "--x: 640px;")).toEqual([]);
  });
});
