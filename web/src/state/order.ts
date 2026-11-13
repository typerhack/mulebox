// The order rules as the page holds them: what the coordinator stores, and the copy being
// edited until Save. One store, so every Order button on the page opens the same rules, and the
// one panel (features/order/OrderButton.tsx) stays open while lanes come and go.
//
// The edits are a change to the rules they were made on (lib/order.ts, changeOf): when the
// rules are read again, only that change is laid over what was read, so a rule another viewer
// changed meanwhile is never sent back as it was. Answers can come back in any order: each
// request takes a turn (lib/turns.ts), a save takes one too, and a read asked before a save is
// dropped; nothing can be edited while a save is on its way, and after it the rules are read again.

import { ApiError, getJson, post, problemText } from "../lib/api";
import { unsent } from "../lib/edits";
import { applyChange, changeOf } from "../lib/order";
import { createStore } from "../lib/store";
import { createTurns } from "../lib/turns";
import type { Rules, RulesBody } from "../lib/types";

const URL = "/api/queue/rules";

export interface OrderState {
  body: RulesBody | null;      // as stored, as last read
  draft: Rules | null;         // as edited; equal to body.rules when nothing is unsaved
  busy: "loading" | "saving" | null;
  said: string | null;         // what the last change did
  problem: string | null;      // why the last request failed, in the server's words
  closed: boolean;             // the server refused changes: its controls are off (405)
  openedBy: string | null;     // the Order button the panel was opened from, while it is open
}

export const EMPTY_ORDER: OrderState =
  { body: null, draft: null, busy: null, said: null, problem: null, closed: false, openedBy: null };
export const orderStore = createStore<OrderState>(EMPTY_ORDER);
const patch = (part: Partial<OrderState>) => orderStore.set((state) => ({ ...state, ...part }));
const turns = createTurns();

// The viewer's edits, as a change to the rules they were made on.
const edits = (state: OrderState): Partial<Rules> =>
  (state.body && state.draft ? changeOf(state.body.rules, state.draft) : {});

// Fresh rules from the server, with `change` (the edits still to save) laid over them.
const rebased = (body: RulesBody, change: Partial<Rules>) => ({ body, draft: applyChange(body.rules, change) });

let reading = false;
export const isReading = () => reading;

// Reads the stored rules. Unsaved edits stay, as a change over what was read.
export async function loadRules(): Promise<void> {
  if (orderStore.get().busy === "saving") return;  // the save reads again when it is done
  const mine = turns.take();
  reading = true;
  patch({ busy: "loading" });
  try {
    const body = await getJson<RulesBody>(URL);
    if (!turns.newest(mine)) return;
    orderStore.set((state) => ({ ...state, ...rebased(body, edits(state)), busy: null,
                                 problem: state.problem?.startsWith("Not loaded.") ? null : state.problem }));
  } catch (failure) {
    if (turns.newest(mine)) patch({ busy: null, problem: `Not loaded. ${problemText(failure)}` });
  } finally {
    if (turns.newest(mine)) reading = false;
  }
}

export const editRules = (change: (rules: Rules) => Rules) =>
  orderStore.set((state) => (state.draft && state.busy !== "saving"
    ? { ...state, draft: change(state.draft), said: null, problem: null } : state));

export const discardRules = () =>
  orderStore.set((state) => ({ ...state, draft: state.body?.rules ?? null, said: null, problem: null }));

async function send(payload: { rules: Partial<Rules> } | { reset: true }, said: string, failed: string) {
  if (orderStore.get().busy === "saving") return;
  turns.take();  // a read on its way is older than this change
  reading = false;
  patch({ busy: "saving", said: null, problem: null });
  try {
    const body = await post<RulesBody>(URL, payload);
    turns.take();
    orderStore.set((state) => {
      const left = "rules" in payload ? unsent(edits(state), payload.rules) : {};
      return { ...state, ...rebased(body, left), busy: null, said };
    });
  } catch (failure) {
    const off = failure instanceof ApiError && failure.status === 405;
    patch({ busy: null, closed: orderStore.get().closed || off,
            problem: off ? "Not saved. This dashboard's controls are off." : `${failed} ${problemText(failure)}` });
  }
  void loadRules();  // the answer may be older than what another viewer saved since
}

export function saveRules(): Promise<void> {
  const state = orderStore.get();
  if (!state.body || !state.draft) return Promise.resolve();
  return send({ rules: edits(state) }, "Saved. The line follows these rules now.", "Not saved.");
}

export const resetRules = () =>
  send({ reset: true }, "Reset. The line is first come, first served again.", "Not reset.");

export const openRules = (from: string) => { patch({ openedBy: from }); void loadRules(); };
export const closeRules = () => patch({ openedBy: null });
