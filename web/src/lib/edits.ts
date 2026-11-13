// The viewer's edits as a change to what was read: what is left of them once a save sent some.
// Shared by the node settings window and the order rules.

const isMap = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

// The edits left once `sent` was saved: an edit still equal to what was sent is done with, one
// the viewer changed since stays. A map's entries count one by one.
export function unsent<T extends object>(draft: Partial<T>, sent: Partial<T>): Partial<T> {
  const left: Record<string, unknown> = { ...draft };
  for (const [key, was] of Object.entries(sent)) {
    const now = left[key];
    if (isMap(now) && isMap(was)) {
      const rest = Object.fromEntries(Object.entries(now).filter(([name, value]) => was[name] !== value));
      if (Object.keys(rest).length) left[key] = rest;
      else delete left[key];
    } else if (now === was) {
      delete left[key];
    }
  }
  return left as Partial<T>;
}
