export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8010";

export type Step = { node: string; detail: string; ms: number };

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
  status: "parsed" | "needs_review" | "skipped" | "failed";
  confidence: number;
  issues: string[];
  sources: Record<string, string>;
  steps: Step[];
  llm_calls: number;
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

export type Session = {
  signed_in: boolean;
  email: string | null;
  gmail_connected: boolean;
  model_configured: boolean;
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
};

export { ApiError };
