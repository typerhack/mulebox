// The whole state library: a value, a way to change it, and a hook that re-renders the
// components reading it (useSyncExternalStore). Live data is replaced whole on every event,
// so a selector that returns a part of it is stable between events.

import { useSyncExternalStore } from "react";

export interface Store<T> {
  get(): T;
  set(next: T | ((current: T) => T)): void;
  subscribe(listener: () => void): () => void;
}

export function createStore<T>(initial: T): Store<T> {
  let value = initial;
  const listeners = new Set<() => void>();
  return {
    get: () => value,
    set(next) {
      const made = typeof next === "function" ? (next as (current: T) => T)(value) : next;
      if (Object.is(made, value)) return;
      value = made;
      listeners.forEach((listener) => listener());
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
  };
}

export function useStore<T>(store: Store<T>): T;
export function useStore<T, S>(store: Store<T>, select: (value: T) => S): S;
export function useStore<T, S>(store: Store<T>, select?: (value: T) => S): T | S {
  return useSyncExternalStore(store.subscribe, () => (select ? select(store.get()) : store.get()));
}
