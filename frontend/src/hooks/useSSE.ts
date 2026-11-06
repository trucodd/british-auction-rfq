import { useEffect, useRef, useState } from "react";

/** Subscribes to a Server-Sent Events stream and calls `onEvent` for every
 *  pushed message. The server only sends "state changed" hints; the client
 *  refetches via its normal REST path, so events can be cheap and droppable.
 *  EventSource reconnects on its own — `connected` reflects the live status
 *  so pages can fall back to (slower) polling while it's down. */
export function useSSE(url: string, onEvent: () => void) {
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource(url);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false); // EventSource auto-retries
    es.onmessage = () => cbRef.current();
    return () => es.close();
  }, [url]);

  return connected;
}
