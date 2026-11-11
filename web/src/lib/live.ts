// A live stream that notices a dead connection. EventSource reports a connection that closes,
// but not one that goes quiet: after a Wi-Fi change or a sleeping dev machine it can wait forever
// with no error. The server sends a `beat` event every few seconds, so a long silence means
// the connection is gone, and the stream is opened again. `url` is asked each time, so a
// reopened stream can resume where it stopped.

const DEAD_AFTER_MS = 20000;
const CHECK_EVERY_MS = 5000;

type Handlers = Record<string, (event: MessageEvent<string>) => void>;
interface Hooks {
  opened?: () => void;
  // `closed` is true when the browser will not retry by itself.
  lost?: (closed: boolean) => void;
}

// Returns a function that ends the stream.
export function liveStream(url: () => string, handlers: Handlers, { opened, lost }: Hooks = {}): () => void {
  let source: EventSource | null = null;
  let heard = 0;
  const hear = () => { heard = performance.now(); };
  const connect = () => {
    source?.close();
    const current = new EventSource(url());
    source = current;
    hear();
    current.onopen = () => { hear(); opened?.(); };
    current.onerror = () => lost?.(current.readyState === EventSource.CLOSED);
    current.addEventListener("beat", hear);
    for (const [name, handle] of Object.entries(handlers)) {
      current.addEventListener(name, (event) => { hear(); handle(event as MessageEvent<string>); });
    }
  };
  connect();
  const watch = setInterval(() => {
    if (performance.now() - heard < DEAD_AFTER_MS) return;
    lost?.(false);
    connect();
  }, CHECK_EVERY_MS);
  return () => { clearInterval(watch); source?.close(); };
}
