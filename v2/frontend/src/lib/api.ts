export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8010";

/** `detail` is the English sentence the backend built; `key`+`params` are the
    same fact for a localised UI to phrase itself. */
export type Step = {
  node: string;
  detail: string;
  ms: number;
  confidence?: number;
  key?: string;
  params?: Record<string, unknown>;
};

export type Transaction = {
  id: string;
  email_id: string | null;
  vendor: string | null;
  amount: number | null;
  tax: number | null;
  subtotal: number | null;
  currency: string;
  order_number: string | null;
  date: string | null;
  category: string | null;
  payment_method: string | null;
  status: "parsed" | "needs_review" | "skipped" | "failed" | "discarded";
  confidence: number;
  issues: string[];
  sources: Record<string, string>;
  steps: Step[];
  model_confidence?: Record<string, number>;
  blocked_on_model?: boolean;
  llm_calls: number;
  thread_id?: string;
  reviewed?: boolean;
};

export type ReviewAnswer = {
  action?: "confirm" | "discard";
  vendor?: string | null;
  amount?: number | null;
  tax?: number | null;
  date?: string | null;
  category?: string | null;
  payment_method?: string | null;
};

export type Notification = {
  id: string;
  kind: string;
  severity: "alert" | "warning" | "info";
  title: string;
  body: string;
  href: string;
  amount: number | null;
  at: string;
  read: boolean;
};

export type NotificationFeed = {
  items: Notification[];
  unread: number;
};

/** Enough of the email a paused thread stopped on to identify it and open the
    original in Gmail. Read from the checkpoint, never stored, and deliberately
    without the body. */
export type ReviewSource = { sender: string | null; subject: string | null };

/** Not a defect in the receipt: the record stalled because the model could not
    be reached. Retrying clears it; reading the email will not. */
export const MODEL_UNAVAILABLE = "model_unavailable";

/* The backend decides this, because it knows which defects `escalate` would
   have been asked to fix. A total that contradicts itself is not one of them:
   a working model is asked twice and still cannot settle it. */
export const blockedOnModel = (row: { blocked_on_model?: boolean; issues: string[] }) =>
  row.blocked_on_model ?? false;

export type ReviewQueue = {
  checkpointer: string;
  items: (Transaction & { live: boolean; source?: ReviewSource | null })[];
  learned: {
    vendors: { domain: string; vendor: string; source: string }[];
    categories: { vendor: string; category: string; source: string }[];
  };
};

export type Stats = {
  total_spent: number;
  receipt_count: number;
  vendor_count: number;
  average: number;
  needs_review: number;
  top_vendors: { name: string; amount: number }[];
  by_category: { name: string; amount: number }[];
  by_month: { month: string; amount: number }[];
};

export type Subscription = {
  vendor: string;
  cadence: string;
  interval_days: number;
  charges: number;
  typical_amount: number;
  baseline_amount: number;
  latest_amount: number;
  annualised: number;
  first_charged: string;
  last_charged: string;
  next_expected: string;
  days_overdue: number;
  price_change_pct: number;
  category: string | null;
};

export type Finding = {
  kind: string;
  severity: "action" | "watch";
  title: string;
  detail: string;
  amount: number;
  transaction_ids: string[];
  vendor?: string | null;
  params?: Record<string, unknown>;
};

export type Insights = {
  subscriptions: Subscription[];
  subscription_summary: {
    count: number;
    annual_commitment: number;
    monthly_equivalent: number;
    price_increases: Subscription[];
    lapsed: Subscription[];
  };
  anomalies: Finding[];
  concentration: {
    total: number;
    vendors: number;
    top_share_pct: number;
    top: { vendor: string; amount: number; share_pct: number }[];
  };
};

export type Statement = {
  available_months: string[];
  month: string;
  total: number;
  prior_total: number;
  delta: number;
  delta_pct: number | null;
  receipts: number;
  tax_paid: number;
  largest: { vendor: string; amount: number; date: string } | null;
  categories: { name: string; amount: number; prior: number; delta: number; share: number }[];
  movers: { name: string; amount: number; delta: number }[];
  daily: { date: string; amount: number }[];
  per_day: number;
  projected: number | null;
};

export type TaxSummary = {
  year: number;
  receipts: number;
  gross: number;
  sales_tax_paid: number;
  effective_tax_rate: number;
  business_apportioned: number;
  by_month: { month: string; tax: number }[];
  by_category: {
    category: string;
    account: string;
    account_name: string;
    business_share: number;
    gross: number;
    tax: number;
    business_apportioned: number;
  }[];
  disclaimer: string;
};

export type Session = {
  signed_in: boolean;
  email: string | null;
  gmail_connected: boolean;
  model_configured: boolean;
  storage: "firestore" | "json";
  linked_legacy_accounts: number;
};

export type RunState = {
  run_id: string;
  status: "starting" | "fetching" | "parsing" | "done" | "failed" | "cancelled";
  total: number;
  done: number;
  saved: number;
  review: number;
  skipped: number;
  error: string | null;
  started_at: string;
};

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new ApiError(response.status, detail.detail ?? response.statusText);
  }
  return response.json() as Promise<T>;
}

export const api = {
  session: () => request<Session>("/api/session"),
  signOut: () => request<Session>("/api/session/end", { method: "POST" }),
  authUrl: () => request<{ url: string }>("/api/google/auth-url"),
  disconnect: () => request<unknown>("/api/google/disconnect", { method: "POST" }),

  startSync: (options: Record<string, unknown> = {}) =>
    request<RunState>("/api/sync", { method: "POST", body: JSON.stringify(options) }),
  stopSync: (runId: string) => request<RunState>(`/api/sync/${runId}/stop`, { method: "POST" }),
  startDemo: () => request<RunState>("/api/demo", { method: "POST" }),

  transactions: (params: Record<string, string> = {}) => {
    const query = new URLSearchParams(params).toString();
    return request<{ transactions: Transaction[] }>(`/api/transactions${query ? `?${query}` : ""}`);
  },
  updateTransaction: (id: string, patch: Partial<Transaction>) =>
    request<Transaction>(`/api/transactions/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteTransaction: (id: string) =>
    request<unknown>(`/api/transactions/${id}`, { method: "DELETE" }),

  stats: () => request<Stats>("/api/stats"),

  notifications: () => request<NotificationFeed>("/api/notifications"),
  markRead: (body: { ids?: string[]; all?: boolean }) =>
    request<NotificationFeed>("/api/notifications/read", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  reviewQueue: () => request<ReviewQueue>("/api/review"),
  // Resumes the paused graph thread for this email; the answer re-enters the
  // graph at await_review and is re-validated before anything is written.
  resolveReview: (emailId: string, answer: ReviewAnswer) =>
    request<{ resumed: boolean; record: Transaction }>(`/api/review/${encodeURIComponent(emailId)}`, {
      method: "POST",
      body: JSON.stringify(answer),
    }),

  insights: () => request<Insights>("/api/insights"),
  statement: (month?: string) =>
    request<Statement>(`/api/statement${month ? `?month=${month}` : ""}`),
  taxSummary: (year?: number) =>
    request<TaxSummary>(`/api/tax-summary${year ? `?year=${year}` : ""}`),
  advisorAsk: (message: string, history: { role: "user" | "assistant"; content: string }[]) =>
    request<{ reply: string; receipts_considered: number }>("/api/advisor/chat", {
      method: "POST",
      body: JSON.stringify({ message, history }),
    }),
  exportUrl: (shape: "ledger" | "journal" | "expenses", month?: string) =>
    `${API_BASE}/api/export/${shape}${month ? `?month=${month}` : ""}`,
};

export { ApiError };
