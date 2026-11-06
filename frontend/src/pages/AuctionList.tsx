import { Link } from "react-router-dom";
import { apiGet } from "../api";
import { usePolling } from "../hooks/usePolling";
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
  const { data, error } = usePolling<RFQSummary[]>(
    () => apiGet("/api/rfqs"),
    3000
  );

  if (error) return <div className="text-red-600">Error: {error}</div>;
  if (!data) return <div>Loading…</div>;
  if (data.length === 0) return <div>No RFQs yet. Click “+ New RFQ”.</div>;

  return (
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
  );
}