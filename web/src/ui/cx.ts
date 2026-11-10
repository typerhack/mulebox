// Join class names, leaving out what is false or empty.
export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");
