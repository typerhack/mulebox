// What this page may change, and the one way it asks (interfaces-m2.md, Controls).
//
// The server gives a token to send back with every change, or null when its controls are off.
// The token is the service's own, or the sign-in's with a password, so after the service
// restarts the old one is refused once: the page then asks for the new one and tries again.

import { getJson } from "./format.js";

let pending = null;

export function actionToken(fresh = false) {
  if (fresh || !pending) {
    pending = getJson("/api/session")
      .then((access) => access?.action_token ?? access?.cancel_token ?? null)
      .catch(() => null);  // no answer: no buttons, the rest of the page still works
  }
  return pending;
}

async function once(url, body, token) {
  return fetch(url, {
    method: "POST",
    headers: { "X-Mulebox-Token": token ?? "", Accept: "application/json",
               ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
}

// The reply's JSON; an Error with `status` and the server's own words when it is refused.
export async function post(url, body = null) {
  let reply = await once(url, body, await actionToken());
  if (reply.status === 403) reply = await once(url, body, await actionToken(true));
  if (!reply.ok) {
    const failure = new Error((await reply.text()).trim());
    failure.status = reply.status;
    throw failure;
  }
  return reply.json();
}
