// The order rules as the page holds them: what the coordinator stores, and the copy being
// edited until Save. One store, so every Order button on the page opens the same rules.

import { ApiError, getJson, post, problemText } from "../lib/api";
import { changeOf } from "../lib/order";
import { createStore } from "../lib/store";
import type { Rules, RulesBody } from "../lib/types";

const URL = "/api/queue/rules";

export interface OrderState {
  body: RulesBody | null;      // as stored
  draft: Rules | null;         // as edited; equal to body.rules when nothing is unsaved
  busy: "loading" | "saving" | null;
  said: string | null;         // what the last change did
  problem: string | null;      // why the last request failed, in the server's words
  closed: boolean;             // the server refused changes: its controls are off (405)
}

export const orderStore = createStore<OrderState>(
  { body: null, draft: null, busy: null, said: null, problem: null, closed: false });
const patch = (part: Partial<OrderState>) => orderStore.set((state) => ({ ...state, ...part }));

// Reads the stored rules. Unsaved edits stay; without any, the copy follows what was read.
export async function loadRules(): Promise<void> {
  patch({ busy: "loading", problem: null });
  try {
    const body = await getJson<RulesBody>(URL);
    orderStore.set((state) => {
      const edited = state.body && state.draft && Object.keys(changeOf(state.body.rules, state.draft)).length > 0;
      return { ...state, body, draft: edited ? state.draft : body.rules, busy: null };
    });
  } catch (failure) {
    patch({ busy: null, problem: `Not loaded. ${problemText(failure)}` });
  }
}

export const editRules = (change: (rules: Rules) => Rules) =>
  orderStore.set((state) => (state.draft ? { ...state, draft: change(state.draft), said: null, problem: null } : state));

export const discardRules = () =>
  orderStore.set((state) => ({ ...state, draft: state.body?.rules ?? null, said: null, problem: null }));

async function send(payload: unknown, said: string, failed: string) {
  patch({ busy: "saving", said: null, problem: null });
  try {
    const body = await post<RulesBody>(URL, payload);
    patch({ body, draft: body.rules, busy: null, said });
  } catch (failure) {
    const off = failure instanceof ApiError && failure.status === 405;
    patch({ busy: null, closed: orderStore.get().closed || off,
            problem: off ? "Not saved. This dashboard's controls are off." : `${failed} ${problemText(failure)}` });
  }
}

export function saveRules(): Promise<void> {
  const { body, draft } = orderStore.get();
  if (!body || !draft) return Promise.resolve();
  return send({ rules: changeOf(body.rules, draft) }, "Saved. The line follows these rules now.", "Not saved.");
}

export const resetRules = () =>
  send({ reset: true }, "Reset. The line is first come, first served again.", "Not reset.");
