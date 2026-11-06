import { Link } from "react-router-dom";
import { apiGet, sseUrl } from "../api";
import { usePolling } from "../hooks/usePolling";
import { useSSE } from "../hooks/useSSE";
import { syncFromServer } from "../serverClock";
import { fmtUtc } from "../time";
import type { RFQSummary } from "../types";

const statusBadge = (s: string) => {
  const map: Record<string, string> = {
    active: "bg-green-100 text-green-800",
    closed: "bg-slate-200 text-slate-700",
    force_closed: "bg-red-100 text-red-800",
  };
  return `px-2 py-0.5 rounded text-xs font-medium ${map[s] ?? ""}`;
};

export default function AuctionList() {
  // Global SSE stream: events carry the updated row itself (lowest bid,
  // current close, status), applied directly — no per-event REST refetch from
  // every open browser tab. 15s polling remains only as a fallback while the
  // stream is disconnected (and for hint-only/unparseable events).
  const { data, error, refresh, setData } = usePolling<RFQSummary[]>(
    () => apiGet("/api/rfqs"),
    15000
  );
  const connected = useSSE(sseUrl("/api/rfqs/stream"), (ev) => {
    syncFromServer(ev.ts); // keep countdowns aligned with the server clock
    const s = ev.summary;
    if (s) {
      setData((prev) => prev
        ? prev.some((r) => r.id === s.id)
          ? prev.map((r) => (r.id === s.id ? s : r))
          : [s, ...prev] // rfq_created
        : prev);
    } else {
      refresh();
    }
  });

  if (error) return <div className="text-red-600">Error: {error}</div>;
  if (!data) return <div>Loading…</div>;
  if (data.length === 0) return <div>No RFQs yet. Click “+ New RFQ”.</div>;

  return (
    <div className="space-y-2">
      <div className="text-xs text-slate-500">
        {connected ? "● live — updates streamed from the server" : "◌ reconnecting — refreshing every 15s"}
      </div>
      <div className="bg-white rounded shadow overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-100 text-left">
          <tr>
            <th className="p-3">Reference</th>
            <th className="p-3">Name</th>
            <th className="p-3">Lowest bid</th>
            <th className="p-3">Current close</th>
            <th className="p-3">Forced close</th>
            <th className="p-3">Status</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r) => (
            <tr key={r.id} className="border-t hover:bg-slate-50">
              <td className="p-3">
                <Link to={`/rfqs/${r.id}`} className="text-blue-600 hover:underline">
                  {r.reference_id}
                </Link>
              </td>
              <td className="p-3">{r.name}</td>
              <td className="p-3">{r.lowest_bid != null ? r.lowest_bid.toFixed(2) : "—"}</td>
              <td className="p-3">{fmtUtc(r.current_close)}</td>
              <td className="p-3">{fmtUtc(r.forced_close)}</td>
              <td className="p-3"><span className={statusBadge(r.status)}>{r.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}