// A line of the server's or the page's words in which `backticks` mark a command: the command
// is set in mono so it reads as one thing to type.

import { codeParts } from "../lib/format";

export const WithCode = ({ text, codeClassName }: { text: string; codeClassName?: string }) => (
  <>
    {codeParts(text).map((part, index) => (part.code
      ? <code key={index} className={codeClassName ?? "font-semibold text-ink-1"}>{part.text}</code>
      : <span key={index}>{part.text}</span>))}
  </>
);
