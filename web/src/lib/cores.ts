// The CPU box's compact view: the busiest cores by name, and one summary for the rest.
// The shown set is kept steady between samples: a core outside it takes a place only when it
// is clearly busier than the quietest one shown, so the rows do not swap on every sample.

export const SWAP_MARGIN = 10; // percentage points

export function busiest(loads: number[], want: number, held: number[] = []): number[] {
  const order = loads.map((_, i) => i).sort((a, b) => loads[b] - loads[a] || a - b);
  const set = held.filter((i) => i < loads.length).slice(0, want);
  for (const i of order) {
    if (set.length >= want) break;
    if (!set.includes(i)) set.push(i);
  }
  for (const i of order.slice(0, want)) {
    if (set.includes(i)) continue;
    const low = set.reduce((a, b) => (loads[a] <= loads[b] ? a : b));
    if (loads[i] > loads[low] + SWAP_MARGIN) set[set.indexOf(low)] = i;
  }
  return set.sort((a, b) => a - b);
}

export interface Rest { count: number; average: number; highest: number }

// The cores not shown: how many, their average and their highest load; null when none are left.
export function rest(loads: number[], shown: number[]): Rest | null {
  const others = loads.filter((_, i) => !shown.includes(i));
  if (!others.length) return null;
  return {
    count: others.length,
    average: others.reduce((a, b) => a + b, 0) / others.length,
    highest: Math.max(...others),
  };
}
