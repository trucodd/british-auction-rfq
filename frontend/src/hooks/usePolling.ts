import { useCallback, useEffect, useRef, useState } from "react";

/** Polls on an interval as the *fallback* data source; callers that also
 *  listen to SSE can call `refresh()` on every pushed event to get updates
 *  instantly (and push the next fallback poll back, so nothing double-fires). */
export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 3000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const liveRef = useRef(true);
  const timerRef = useRef<number | undefined>(undefined);

  const run = useCallback(async () => {
    try {
      const d = await fetcherRef.current();
      if (liveRef.current) { setData(d); setError(null); }
    } catch (e) {
      if (liveRef.current) setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const schedule = useCallback(() => {
    if (!liveRef.current) return;
    clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(async () => {
      await run();
      schedule();
    }, intervalMs);
  }, [intervalMs, run]);

  useEffect(() => {
    liveRef.current = true;
    run().finally(schedule);
    return () => {
      liveRef.current = false;
      clearTimeout(timerRef.current);
    };
  }, [run, schedule]);

  const refresh = useCallback(async () => {
    if (!liveRef.current) return;
    await run();
    schedule(); // reschedule: the push replaced this cycle's fetch
  }, [run, schedule]);

  return { data, error, refresh };
}
