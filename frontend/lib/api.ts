// Typed client for the FastAPI backend. The frontend talks to nothing else:
// no Supabase, no OpenRouter, no keys.

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError("network", `Can't reach the backend at ${API_BASE}. Check that it is running.`);
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // fall through: handled below
  }
  if (!response.ok) {
    const err = body as { error?: string; message?: string } | null;
    throw new ApiError(
      err?.error ?? "http_error",
      err?.message ?? `The backend answered with an error (${response.status}).`,
      response.status,
    );
  }
  if (body === null) throw new ApiError("bad_response", "The backend sent a reply this page couldn't read.");
  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    }),
};

// ---- Response types (mirror backend/app/schemas.py) -------------------------

export type RunStatus = "running" | "done" | "failed";

export interface RunInfo {
  run_id: string;
  status: RunStatus;
  started_at: string | null;
  finished_at: string | null;
  period_start: string | null;
  period_end: string | null;
  model_a_id: string | null;
  model_b_id: string | null;
  counts: Record<string, unknown>;
  cost_usd: number | null;
  error: string | null;
}

export interface RunList {
  runs: RunInfo[];
}

export interface DateRange {
  first_order_date: string | null;
  last_order_date: string | null;
}

export type CoverageKey = "classified" | "junk" | "unmatched" | "unclassified";

export interface CoverageItem {
  key: CoverageKey;
  label: string;
  count: number;
  share: number | null;
}

export type ReasonGroup = "vendor" | "unclear" | "not_vendor" | "other";

export interface ReasonCount {
  reason: string;
  label: string;
  group: ReasonGroup;
  likely_owner: string;
  count: number;
  share: number | null;
}

export interface Summary {
  run: RunInfo;
  other_returns: number;
  dropdown_returns_not_analysed: number;
  units_sold: number;
  coverage: CoverageItem[];
  reasons: ReasonCount[];
  routed_to_model_b: number;
  flagged_vendors: number;
}

export interface Cell {
  reason: string;
  label: string;
  can_flag: boolean;
  returns: number;
  rate: number | null;
  category_avg: number | null;
  lift: number | null;
  flagged: boolean;
}

export interface VendorSku {
  sku_id: string;
  product_name: string | null;
  is_live: boolean | null;
  units_sold: number;
  returns: number;
  rates: { reason: string; returns: number; rate: number | null }[];
}

export interface VendorRow {
  vendor_id: string;
  vendor_name: string;
  city: string | null;
  category: string;
  category_label: string;
  units_sold: number;
  returns_total: number;
  cells: Cell[];
  flagged: boolean;
  skus: VendorSku[];
}

export interface Thresholds {
  min_returns_to_flag: number;
  lift_threshold: number;
}

export interface Vendors {
  run: RunInfo;
  thresholds: Thresholds;
  category: string | null;
  rows: VendorRow[];
  unclassified: number;
  unmatched: number;
}

export interface Comment {
  return_id: string;
  text: string;
  gist_en: string | null;
  reason: string | null;
  reason_label: string | null;
  fit_direction_label: string | null;
  secondary_reason: string | null;
  size: string | null;
  product_name: string | null;
  model_used: string | null;
  confidence: number | null;
}

export interface NonVendorGroup {
  reason: string;
  label: string;
  likely_owner: string;
  count: number;
  share: number | null;
  examples: Comment[];
}

export interface NonVendor {
  run: RunInfo;
  classified_total: number;
  groups: NonVendorGroup[];
}

export interface GapExample {
  return_id: string;
  text: string;
  why: string | null;
  order_line_id: string | null;
}

export interface GapBucket {
  key: "unmatched" | "junk" | "unclassified";
  label: string;
  explainer: string;
  count: number;
  examples: GapExample[];
}

export interface Gaps {
  run: RunInfo;
  total: number;
  buckets: GapBucket[];
}

export interface Preview {
  status: "classified" | "junk" | "unclassified";
  scrubbed_text: string;
  classification: {
    reason: string;
    fit_direction: string | null;
    fit_area: string | null;
    secondary_reason: string | null;
    confidence: number;
    gist_en: string;
  } | null;
  reason_label: string | null;
  fit_direction_label: string | null;
  likely_owner: string | null;
  model_used: "A" | "B" | "none";
  routed: boolean;
  confidence_threshold: number;
  detail: string | null;
}
