export type RFQStatus = "active" | "closed" | "force_closed";

export interface AuctionConfig {
  trigger_window_minutes: number;
  extension_minutes: number;
  trigger_on_bid: boolean;
  trigger_on_any_rank_change: boolean;
  trigger_on_l1_change: boolean;
}

export interface Bid {
  id: number;
  supplier_name: string;
  freight_charge: number;
  origin_charge: number;
  destination_charge: number;
  total_price: number;
  transit_days: number;
  quote_valid_until: string;
  created_at: string;
  rank?: number | null;
}

export interface ActivityLog {
  id: number;
  event_type: "BID" | "EXTENSION" | "CLOSE" | "FORCE_CLOSE";
  reason: string | null;
  old_close: string | null;
  new_close: string | null;
  extra: Record<string, unknown> | null;
  created_at: string;
}

export interface RFQSummary {
  id: number;
  reference_id: string;
  name: string;
  pickup_date: string;
  bid_start: string;
  original_close: string;
  current_close: string;
  forced_close: string;
  status: RFQStatus;
  lowest_bid: number | null;
}

export interface RFQDetail extends RFQSummary {
  config: AuctionConfig;
  bids: Bid[];
  logs: ActivityLog[];
}