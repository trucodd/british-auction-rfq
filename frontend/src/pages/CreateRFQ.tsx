import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiPost } from "../api";
import { localInputToUtcIso } from "../time";
import type { RFQSummary } from "../types";

export default function CreateRFQ() {
  const nav = useNavigate();
  const [form, setForm] = useState({
    reference_id: "",
    name: "",
    pickup_date: "",
    bid_start: "",
    bid_close: "",
    forced_close: "",
    trigger_window_minutes: 10,
    extension_minutes: 5,
    trigger_on_bid: true,
    trigger_on_any_rank_change: false,
    trigger_on_l1_change: true,
  });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const upd = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) =>
    setForm({ ...form, [k]: v });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const created = await apiPost<RFQSummary>("/api/rfqs", {
        reference_id: form.reference_id,
        name: form.name,
        pickup_date: localInputToUtcIso(form.pickup_date),
        bid_start: localInputToUtcIso(form.bid_start),
        bid_close: localInputToUtcIso(form.bid_close),
        forced_close: localInputToUtcIso(form.forced_close),
        config: {
          trigger_window_minutes: Number(form.trigger_window_minutes),
          extension_minutes: Number(form.extension_minutes),
          trigger_on_bid: form.trigger_on_bid,
          trigger_on_any_rank_change: form.trigger_on_any_rank_change,
          trigger_on_l1_change: form.trigger_on_l1_change,
        },
      });
      nav(`/rfqs/${created.id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="bg-white rounded shadow p-6 space-y-3 max-w-2xl">
      <h1 className="text-lg font-semibold">Create RFQ</h1>
      <input required placeholder="Reference ID (e.g. RFQ-001)" value={form.reference_id}
             onChange={(e) => upd("reference_id", e.target.value)} className="border p-2 rounded w-full" />
      <input required placeholder="RFQ name" value={form.name}
             onChange={(e) => upd("name", e.target.value)} className="border p-2 rounded w-full" />
      <label className="block text-sm text-slate-600">Pickup date
        <input required type="datetime-local" value={form.pickup_date}
               onChange={(e) => upd("pickup_date", e.target.value)} className="border p-2 rounded w-full mt-1" />
      </label>
      <label className="block text-sm text-slate-600">Bid start
        <input required type="datetime-local" value={form.bid_start}
               onChange={(e) => upd("bid_start", e.target.value)} className="border p-2 rounded w-full mt-1" />
      </label>
      <label className="block text-sm text-slate-600">Bid close
        <input required type="datetime-local" value={form.bid_close}
               onChange={(e) => upd("bid_close", e.target.value)} className="border p-2 rounded w-full mt-1" />
      </label>
      <label className="block text-sm text-slate-600">Forced bid close (must be later)
        <input required type="datetime-local" value={form.forced_close}
               onChange={(e) => upd("forced_close", e.target.value)} className="border p-2 rounded w-full mt-1" />
      </label>

      <div className="grid grid-cols-2 gap-3 pt-2">
        <label className="block text-sm text-slate-600">Trigger window X (min)
          <input required type="number" min={1} value={form.trigger_window_minutes}
                 onChange={(e) => upd("trigger_window_minutes", Number(e.target.value))}
                 className="border p-2 rounded w-full mt-1" />
        </label>
        <label className="block text-sm text-slate-600">Extension Y (min)
          <input required type="number" min={1} value={form.extension_minutes}
                 onChange={(e) => upd("extension_minutes", Number(e.target.value))}
                 className="border p-2 rounded w-full mt-1" />
        </label>
      </div>

      <div className="space-y-1 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={form.trigger_on_bid}
                 onChange={(e) => upd("trigger_on_bid", e.target.checked)} />
          Extend on bid received in last X minutes
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={form.trigger_on_any_rank_change}
                 onChange={(e) => upd("trigger_on_any_rank_change", e.target.checked)} />
          Extend on any supplier rank change
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={form.trigger_on_l1_change}
                 onChange={(e) => upd("trigger_on_l1_change", e.target.checked)} />
          Extend on L1 (lowest bidder) change
        </label>
      </div>

      {err && <div className="text-red-600 text-sm">{err}</div>}
      <button disabled={busy} className="bg-blue-600 text-white px-4 py-2 rounded">
        {busy ? "Creating…" : "Create RFQ"}
      </button>
    </form>
  );
}