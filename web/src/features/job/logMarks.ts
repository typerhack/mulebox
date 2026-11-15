// Finds the test runners' own summary lines in a job's log on the page, to underline them and
// to go to them (design-system/tests/, option B). The lines are the ones the coordinator counted
// (mulebox/common/test_counts.py, `tests.lines`), found by their text. The log stays text: the
// lines are marked as ranges through the CSS Custom Highlight API, with no element added; a
// browser without it still gets the jump.

const NAME = "test-summary", NAME_BAD = "test-summary-failed";

// The log's lines that read as one of `wanted`, in the order of `wanted`, then as they come.
export function summaryRanges(box: HTMLElement, wanted: string[]): Range[] {
  const found: [number, number, Range][] = [];
  const texts = wanted.map((line) => line.trimEnd());
  let order = 0;
  for (const node of box.childNodes) {
    if (node.nodeType !== Node.TEXT_NODE) continue;
    const text = node.nodeValue ?? "";
    for (let from = 0; from < text.length;) {
      const end = text.indexOf("\n", from), to = end < 0 ? text.length : end;
      const line = text.slice(from, to);
      const which = texts.indexOf(line.trimEnd());
      if (which >= 0) {
        const range = document.createRange();
        range.setStart(node, from);
        range.setEnd(node, to);
        found.push([which, order++, range]);
      }
      from = to + 1;
    }
  }
  return found.sort((a, b) => a[0] - b[0] || a[1] - b[1]).map((item) => item[2]);
}

// Underlines them, in the failed colour when the count failed the job. Returns the ranges.
export function underlineSummaries(box: HTMLElement | null, wanted: string[], failed: boolean): Range[] {
  clearSummaries();
  if (!box) return [];
  const ranges = summaryRanges(box, wanted);
  if (ranges.length && typeof CSS !== "undefined" && CSS.highlights && typeof Highlight !== "undefined") {
    CSS.highlights.set(failed ? NAME_BAD : NAME, new Highlight(...ranges));
  }
  return ranges;
}

export function clearSummaries() {
  if (typeof CSS === "undefined" || !CSS.highlights) return;
  CSS.highlights.delete(NAME);
  CSS.highlights.delete(NAME_BAD);
}

// Scrolls the log to the first summary line (of the runners that fell short first), or to its end when
// none is on the page, and puts the focus in the log.
export function toSummary(box: HTMLElement | null, wanted: string[], failed: boolean) {
  if (!box) return;
  const [first] = underlineSummaries(box, wanted, failed);
  const top = first?.getBoundingClientRect?.().top;
  box.scrollTop = top === undefined ? box.scrollHeight
    : Math.max(0, box.scrollTop + top - box.getBoundingClientRect().top - box.clientHeight / 3);
  box.scrollIntoView({ block: "nearest" });
  box.focus();
}
