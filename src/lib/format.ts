// Formatting helpers for Indian financial figures.

const inrGrouping = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** ₹8,499 — standard Indian digit grouping. */
export function formatINR(n: number): string {
  if (!Number.isFinite(n)) return "₹0";
  return `₹${inrGrouping.format(Math.round(n))}`;
}

/** ₹42.7L / ₹18.42L — lakh shorthand used for large aggregates. */
export function formatLakh(n: number, decimals = 2): string {
  if (!Number.isFinite(n)) return "₹0L";
  const lakh = n / 100000;
  const fixed = lakh.toFixed(decimals).replace(/\.?0+$/, "");
  return `₹${fixed}L`;
}

/** 74% — whole percent. */
export function formatPct(n: number, decimals = 0): string {
  if (!Number.isFinite(n)) return "0%";
  return `${n.toFixed(decimals)}%`;
}

/** "Aug 28 · 09:00" style timestamps. */
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  const date = d.toLocaleDateString("en-IN", { month: "short", day: "numeric" });
  const time = d.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${date} · ${time}`;
}

/** "10:42:11" — audit trail clock time. */
export function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export const FAILURE_LABELS: Record<string, string> = {
  INSUFFICIENT_FUNDS: "Insufficient Funds",
  EXPIRED_CARD: "Expired Card",
  NETWORK_FAILURE: "Network Failure",
  BANK_DECLINE: "Bank Decline",
  INVALID_DETAILS: "Invalid Details",
  OTHER: "Other",
};

export const ACTION_LABELS: Record<string, string> = {
  RETRY: "Retry",
  PAYMENT_UPDATE: "Payment Update",
  NOTIFY: "Customer Notification",
  STOP: "Stop",
  ESCALATE: "Escalate",
};

export const STATUS_LABELS: Record<string, string> = {
  QUEUED: "Queued",
  SCHEDULED: "Scheduled",
  PROCESSING: "Processing",
  RECOVERED: "Recovered",
  HALTED: "Halted",
  NEEDS_ACTION: "Needs Action",
};

export const METHOD_LABELS: Record<string, string> = {
  UPI: "UPI",
  CARD: "Card",
  NET_BANKING: "Net Banking",
};
