// A line that may be longer than its box: cut with an ellipsis, the whole text in its tooltip,
// and a small button beside it that copies the whole text (a check for a moment once copied).

import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";

import { cx } from "./cx";
import { Tip } from "./Tip";

export function CopyText({ text, title, className }: { text: string; title?: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);
  const copy = () => {
    navigator.clipboard?.writeText(text).then(() => setCopied(true), () => undefined);
  };
  const Icon = copied ? Check : Copy;
  return (
    <span className={cx("inline-flex min-w-0 max-w-full items-center gap-1", className)}>
      <Tip text={title ? `${title}: ${text}` : text}>
        <span className="min-w-0 truncate">{text}</span>
      </Tip>
      <Tip text={copied ? "Copied" : "Copy"}>
        <button type="button" onClick={copy} aria-label={copied ? "Copied" : `Copy ${title ?? "text"}`}
          className="inline-grid flex-none place-items-center rounded-s p-1 text-ink-3 transition-colors hover:bg-surface-3 hover:text-ink-1">
          <Icon aria-hidden className="size-icon-s" />
        </button>
      </Tip>
    </span>
  );
}
