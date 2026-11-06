/** Server clock sync.

 *  The backend validates all close/extension times with its own clock, so the
 *  client must never trust the browser's local clock: a machine even 1s ahead
 *  could show a 2s remaining countdown for an auction the server considers
 *  closed. Every SSE event carries `ts` (= server epoch ms); we track the
 *  offset and any countdown math runs against `serverNow()`.
 */

let offsetMs = 0;

export function syncFromServer(serverTsMs: number | undefined): void {
  if (typeof serverTsMs === "number" && Number.isFinite(serverTsMs)) {
    offsetMs = serverTsMs - Date.now();
  }
}

/** Current time as the server sees it (best estimate). */
export function serverNow(): Date {
  return new Date(Date.now() + offsetMs);
}
