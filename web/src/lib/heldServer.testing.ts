// For tests: a stand-in server whose answers the test gives one by one, in the order it
// chooses, so answers can come back out of order. Until `hold()`, every request is answered at
// once with what `answer` gives for it. Used by the node settings window and the order panel.

import { act } from "@testing-library/react";
import { vi } from "vitest";

export interface Held { url: string; post: boolean; body: unknown; answer: (with_: unknown) => Promise<void> }

export const reply = (body: unknown, status = 200) => Promise.resolve(new Response(
  typeof body === "string" ? body : JSON.stringify(body), { status }));

export function heldServer(answer: (url: string, post: boolean) => unknown) {
  const asked: Held[] = [];
  let held = false;
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (url === "/api/session") return reply({ action_token: "token" });
    const post = init?.method === "POST";
    const body = post ? JSON.parse(String(init?.body)) : null;
    if (!held) { asked.push({ url, post, body, answer: async () => {} }); return reply(answer(url, post)); }
    return new Promise<Response>((resolve) => {
      asked.push({ url, post, body, answer: (with_) => act(async () => { resolve(await reply(with_)); }) });
    });
  }));
  return { asked, hold: () => { held = true; asked.length = 0; }, release: () => { held = false; },
           gets: () => asked.filter((one) => !one.post), posts: () => asked.filter((one) => one.post) };
}
