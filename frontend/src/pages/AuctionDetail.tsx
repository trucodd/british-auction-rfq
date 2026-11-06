import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiGet, apiPost, sseUrl } from "../api";
import { usePolling } from "../hooks/usePolling";
import { useSSE } from "../hooks/useSSE";
import { serverNow, syncFromServer } from "../serverClock";
import { fmtUtc, parseUtc } from "../time";
import type { Bid, RFQDetail } from "../types";

function Countdown({ closeIso }: { closeIso: string }) {
  // Rerenders every second. The comparison runs against the server-synced
  // clock, never the browser's — a skewed local clock must not show "2s
  // left" for an auction the server already closed.
  const [, tick] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, []);

  const ms = parseUtc(closeIso).getTime() - serverNow().getTime();
  if (ms <= 0) return <div className="font-semibold text-red-600">time is up</div>;
  const totalSec = Math.floor(ms / 1000);
  const mm = Math.floor(totalSec / 60);
  const ss = String(totalSec % 60).padStart(2, "0");
  return (
    <div className={`font-mono font-semibold ${mm < 1 ? "text-red-600" : "text-blue-700"}`}>
      {mm}:{ss}
    </div>
  );
}

function BidForm({ rfqId, disabled }: { rfqId: number; disabled: boolean }) {
  const [form, setForm] = useState({
    supplier_name: "",
    freight_charge: "",
    origin_charge: "",
    destination_charge: "",
    transit_days: "",
    quote_valid_until: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      await apiPost<Bid>(`/api/rfqs/${rfqId}/bids`, {
        supplier_name: form.supplier_name,
        freight_charge: Number(form.freight_charge),
        origin_charge: Number(form.origin_charge),
        destination_charge: Number(form.destination_charge),
        transit_days: Number(form.transit_days),
        quote_valid_until: new Date(form.quote_valid_until).toISOString().slice(0, 19),
      });
      setForm({ ...form, supplier_name: "", freight_charge: "", origin_charge: "",
                destination_charge: "", transit_days: "", quote_valid_until: "" });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-2 text-sm bg-slate-50 p-4 rounded">
      <input required placeholder="Supplier name" value={form.supplier_name}
             onChange={set("supplier_name")} className="border p-2 rounded col-span-2" />
      <input required type="number" step="0.01" placeholder="Freight" value={form.freight_charge}
             onChange={set("freight_charge")} className="border p-2 rounded" />
      <input required type="number" step="0.01" placeholder="Origin" value={form.origin_charge}
             onChange={set("origin_charge")} className="border p-2 rounded" />
      <input required type="number" step="0.01" placeholder="Destination" value={form.destination_charge}
             onChange={set("destination_charge")} className="border p-2 rounded" />
      <input required type="number" placeholder="Transit days" value={form.transit_days}
             onChange={set("transit_days")} className="border p-2 rounded" />
      <input required type="datetime-local" value={form.quote_valid_until}
             onChange={set("quote_valid_until")} className="border p-2 rounded col-span-2" />
      <button disabled={submitting || disabled}
              className="col-span-2 bg-blue-600 text-white py-2 rounded disabled:opacity-50">
        {disabled ? "Auction closed" : submitting ? "Submitting…" : "Place bid"}
      </button>
      {err && <div className="col-span-2 text-red-600">{err}</div>}
    </form>
  );
}

export default function AuctionDetail() {
  const { id } = useParams();
  const rfqId = Number(id);

  // SSE pushes the updated state itself (bid+rankings, extended close, status
  // flips) and those payloads are applied directly — no per-event REST
  // refetch. The 15s poll stays only as a fallback while the stream is down,
  // and hint-only/unparseable events resync through `refresh()`.
  const { data, error, refresh, setData } = usePolling<RFQDetail>(
    () => apiGet(`/api/rfqs/${rfqId}`),
    15000
  );
  const connected = useSSE(sseUrl(`/api/rfqs/${rfqId}/stream`), (ev) => {
    syncFromServer(ev.ts); // keep the countdown aligned with the server clock
    if (ev.detail) setData(ev.detail);
    else refresh();
  });

  if (error) return <div className="text-red-600">{error}</div>;
  if (!data) return <div>Loading…</div>;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded shadow p-5">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">{data.name}</h1>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500"
                  title={connected ? "Streaming live updates" : "Stream down — refreshing every 15s"}>
              {connected ? "● live" : "◌ reconnecting"}
            </span>
            <span className="text-xs uppercase px-2 py-1 rounded bg-slate-200">{data.status}</span>
          </div>
        </div>
        <div className="text-sm text-slate-600 mt-1">
          Ref {data.reference_id} · pickup {fmtUtc(data.pickup_date)}
        </div>
        <div className="grid grid-cols-3 gap-4 mt-4 text-sm">
          <div>
            <div className="text-slate-500">Original close</div>
            <div>{fmtUtc(data.original_close)}</div>
          </div>
          <div>
            <div className="text-slate-500">Current close</div>
            <Countdown closeIso={data.current_close} />
            <div>{fmtUtc(data.current_close)}</div>
          </div>
          <div>
            <div className="text-slate-500">Forced close</div>
            <div>{fmtUtc(data.forced_close)}</div>
          </div>
        </div>
        <div className="text-xs text-slate-500 mt-3">
          Config — X: {data.config.trigger_window_minutes}m, Y: {data.config.extension_minutes}m ·
          triggers: {[
            data.config.trigger_on_bid && "bid",
            data.config.trigger_on_any_rank_change && "any rank",
            data.config.trigger_on_l1_change && "L1",
          ].filter(Boolean).join(", ") || "none"}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 space-y-3">
          <h2 className="font-semibold">Bids</h2>
          <div className="bg-white rounded shadow overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-100 text-left">
                <tr>
                  <th className="p-2">Rank</th>
                  <th className="p-2">Supplier</th>
                  <th className="p-2">Total</th>
                  <th className="p-2">Freight / Origin / Dest</th>
                  <th className="p-2">Transit</th>
                  <th className="p-2">Valid until</th>
                  <th className="p-2">Submitted</th>
                </tr>
              </thead>
              <tbody>
                {data.bids.map((b) => (
                  <tr key={b.id} className="border-t">
                    <td className="p-2 font-semibold">L{b.rank}</td>
                    <td className="p-2">{b.supplier_name}</td>
                    <td className="p-2 font-mono">{b.total_price.toFixed(2)}</td>
                    <td className="p-2 text-slate-600">
                      {b.freight_charge} / {b.origin_charge} / {b.destination_charge}
                    </td>
                    <td className="p-2">{b.transit_days}d</td>
                    <td className="p-2 text-slate-600">{fmtUtc(b.quote_valid_until)}</td>
                    <td className="p-2 text-slate-500">{fmtUtc(b.created_at)}</td>
                  </tr>
                ))}
                {data.bids.length === 0 && (
                  <tr><td className="p-4 text-slate-500" colSpan={7}>No bids yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <h2 className="font-semibold pt-4">Place a bid</h2>
          <BidForm rfqId={data.id} disabled={data.status !== "active"} />
        </div>

        <div>
          <h2 className="font-semibold mb-2">Activity</h2>
          <div className="space-y-2 max-h-[600px] overflow-y-auto">
            {data.logs.map((l) => (
              <div key={l.id} className="bg-white rounded shadow p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{l.event_type}</span>
                  <span className="text-xs text-slate-500">{fmtUtc(l.created_at)}</span>
                </div>
                {l.reason && <div className="text-slate-700 mt-1">{l.reason}</div>}
                {l.event_type === "EXTENSION" && (
                  <div className="text-xs text-slate-500 mt-1">
                    {fmtUtc(l.old_close)} → {fmtUtc(l.new_close)}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}