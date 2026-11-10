// The History page's search box: what is typed is searched once typing stops for SEARCH_MS
// (lib/history.ts), or at once on Enter; the cross clears it.

import { Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { SEARCH_MS, debounce } from "../../lib/history";
import { IconButton } from "../../ui/Button";

interface Props {
  value: string;                       // the search in force, from the hash
  onSearch: (text: string) => void;
}

export function HistorySearch({ value, onSearch }: Props) {
  const [typed, setTyped] = useState(value);
  const [shown, setShown] = useState(value);
  if (shown !== value) {  // changed from outside, such as "Clear filters" or a link
    setShown(value);
    setTyped(value);
  }
  const latest = useRef(onSearch);
  useEffect(() => { latest.current = onSearch; });
  const later = useMemo(() => debounce((text: string) => latest.current(text.trim()), SEARCH_MS), []);
  useEffect(() => later.cancel, [later]);

  const type = (text: string) => { setTyped(text); later(text); };
  const now = (text: string) => { later.cancel(); setTyped(text); onSearch(text.trim()); };

  return (
    <div className="relative min-w-0 flex-1 basis-col-m">
      <Search aria-hidden size={16} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-3" />
      <input type="search" value={typed} enterKeyHint="search" aria-label="Search project, job or branch"
        placeholder="Search project, job or branch"
        onChange={(event) => type(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") now(typed);
          if (event.key === "Escape" && typed) { event.preventDefault(); now(""); }
        }}
        className="h-ctl touch:h-ctl-touch w-full min-w-0 appearance-none rounded-m border border-line-strong bg-surface-1 pr-ctl pl-ctl text-base text-ink-1 placeholder:text-ink-3" />
      {typed && (
        <IconButton small label="Clear the search" onClick={() => now("")}
          className="absolute top-1/2 right-1 -translate-y-1/2 border-transparent">
          <X aria-hidden size={16} />
        </IconButton>
      )}
    </div>
  );
}
