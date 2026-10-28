// Client for the local companion API. The CSRF token lives only in memory.

export type View = "review" | "approved" | "all" | "included" | "deprioritized" | "skipped" | "withheld" | "pending";

export interface MessageSummary {
  id: string; received_at: string; sender: string; sender_address: string; subject: string;
  relevance: string; reason: string; privacy_hold: string | null; model_relevance: string | null;
  state: string; error: string | null; language: string | null; labels: string[];
  fact_counts?: Record<string, number>;
}

export interface Fact {
  id: string; status: "proposed" | "approved" | "dismissed" | "superseded"; category: string;
  local_text: string; outgoing_text: string; evidence: { message_id: string; quote: string }[];
  privacy_flags: string[]; release_blocked: string | null; edited: boolean;
  model: string; prompt_version: string; created_at: string; message?: MessageSummary;
}

export interface MessageDetail extends MessageSummary {
  body: string | null; coverage: Record<string, boolean>; facts: Fact[];
  thread: { id: string; received_at: string; sender: string; subject: string; state: string }[];
  gmail_url: string; sender_override: "include" | "exclude" | null;
}

export interface Status {
  account: string | null; connected: boolean; progress: { phase: string; detail: string };
  last_sync_at: string | null; sync_error: string | null;
  coverage: { window_days?: number; max_messages?: number; listed?: number; capped?: boolean; since?: string };
  message_states: Record<string, number>; fact_states: Record<string, number>; views: Record<string, number>;
  model_unavailable: string | null; policy_version: string;
}

let csrf = "";

async function request<T>(method: string, path: string, body?: unknown, auth?: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && csrf) headers["X-CSRF-Token"] = csrf;
  if (auth) headers.Authorization = `Bearer ${auth}`;
  const response = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: "same-origin" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(payload.error ?? `HTTP ${response.status}`), { status: response.status, payload });
  return payload as T;
}

/** Returns "live" (paired), "pair" (companion present, not paired), or "demo" (no companion). */
export async function detectMode(): Promise<"live" | "pair" | "demo"> {
  try {
    const response = await fetch("/api/session", { credentials: "same-origin" });
    if (!(response.headers.get("Content-Type") ?? "").startsWith("application/json")) return "demo";
    if (response.status === 401) return "pair";
    if (!response.ok) return "demo";
    csrf = (await response.json()).csrf;
    return "live";
  } catch {
    return "demo";
  }
}

export async function pair(code: string): Promise<void> {
  csrf = (await request<{ csrf: string }>("POST", "/api/session", {}, code.trim())).csrf;
}

export const api = {
  status: () => request<Status>("GET", "/api/status"),
  messages: (view: View, q: string, from: string, to: string) =>
    request<{ messages: MessageSummary[] }>("GET", `/api/messages?${new URLSearchParams({ view, q, from, to })}`),
  message: (id: string) => request<MessageDetail>("GET", `/api/messages/${id}`),
  facts: (status: "proposed" | "approved") => request<{ facts: Fact[] }>("GET", `/api/facts?status=${status}`),
  factAction: (id: string, action: "approve" | "dismiss" | "edit" | "reopen", text?: string) =>
    request<Fact>("POST", `/api/facts/${id}`, text === undefined ? { action } : { action, text }),
  refresh: () => request("POST", "/api/refresh", {}),
  retryFailed: () => request("POST", "/api/retry-failed", {}),
  sender: (address: string, action: "include" | "exclude" | null) => request("POST", "/api/senders", { address, action }),
  preview: (tool: string, args: Record<string, unknown>) => request<{ result: unknown }>("POST", "/api/preview", { tool, arguments: args }),
  logout: () => request("POST", "/api/logout", {}),
};

export const reasonLabels: Record<string, string> = {
  user_excluded: "You excluded this sender", user_included: "You included this sender", gmail_spam: "Gmail spam",
  gmail_trash: "Gmail trash", gmail_draft: "Draft", selected_sender: "Selected sender", tracked_thread: "Thread has approved facts",
  starred: "Starred in Gmail", security_alert: "Security alert", failure_or_cancellation: "Failure or cancellation",
  promotion: "Gmail Promotions", newsletter: "Newsletter list", routine_receipt: "Routine receipt",
  routine_shipment: "Routine shipment", direct_request: "Direct request", changed_date: "Changed date",
  explicit_decision: "Explicit decision", uncertain: "No rule matched",
};

export const holdLabels: Record<string, string> = {
  unsupported_language: "Language not supported yet (English only). Never sent to the model.",
  sensitive_topic: "Sensitive topic (medical, financial, intimate). Kept for local viewing only.",
};

export const blockLabels: Record<string, string> = {
  not_approved: "Not approved yet", policy_changed: "Privacy policy changed since review",
  flagged_identifier: "Contains a detected identifier — edit it out first", final_privacy_check: "Final privacy check found an identifier",
};
