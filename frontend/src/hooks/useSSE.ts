import { useEffect, useRef, useState } from "react";
import type { SSEEvent } from "../types";

/** Subscribes to a Server-Sent Events stream and hands every pushed message
 *  (already parsed) to `onEvent`. Events carry the updated state, so consumers
 *  normally apply the payload directly; only events without a usable payload
 *  fall back to a REST refetch. EventSource reconnects on its own — `connected`
 *  reflects the live status so pages can fall back to (slower) polling. */
export function useSSE(url: string, onEvent: (ev: SSEEvent) => void) {
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource(url);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false); // EventSource auto-retries
    es.onmessage = (msg) => {
      try {
        cbRef.current(JSON.parse(msg.data) as SSEEvent);
      } catch {
        cbRef.current({ type: "unknown" }); // unparseable → caller may resync
      }
    };
    return () => es.close();
  }, [url]);

  return connected;
}
