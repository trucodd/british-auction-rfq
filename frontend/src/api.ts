const BASE = import.meta.env.VITE_API_BASE ?? "";

/** Full URL for an SSE endpoint (EventSource doesn't go through a helper). */
export const sseUrl = (path: string) => `${BASE}${path}`;

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`POST ${path} → ${r.status} ${text}`);
  }
  return r.json();
}