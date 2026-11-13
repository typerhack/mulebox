// Answers that can come back in any order (the node settings window, the order rules). Every
// request takes the next turn, and its answer is used only while that turn is still the newest;
// a change takes a turn too, so a read asked before it can never undo it.

export const REREAD_MS = 5000;  // how often an open window or panel asks again while visible

export interface Turns {
  take(): number;                    // a request's turn, and the newest from now on
  newest(turn: number): boolean;     // whether nothing was asked after it
}

export function createTurns(): Turns {
  let at = 0;
  return { take: () => (at += 1), newest: (turn) => turn === at };
}
