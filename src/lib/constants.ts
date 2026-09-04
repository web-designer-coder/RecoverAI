// Shared UI constants — single source for filter/category lists that were
// previously duplicated across route files.

import type { RecoveryStatus } from "./types";

/** Status chips on the recovery queue, in display order. */
export const QUEUE_FILTERS = [
  "ALL",
  "HIGH_PRIORITY",
  "QUEUED",
  "SCHEDULED",
  "PROCESSING",
  "RECOVERED",
  "HALTED",
  "NEEDS_ACTION",
] as const;

export type QueueFilter = (typeof QUEUE_FILTERS)[number];

const QUEUE_FILTER_LABELS: Record<QueueFilter, string> = {
  ALL: "All",
  HIGH_PRIORITY: "High Priority",
  QUEUED: "Queued",
  SCHEDULED: "Scheduled",
  PROCESSING: "Processing",
  RECOVERED: "Recovered",
  HALTED: "Halted",
  NEEDS_ACTION: "Needs Action",
};

export function queueFilterLabel(f: string): string {
  return QUEUE_FILTER_LABELS[f as QueueFilter] ?? f;
}

/** Valid RecoveryStatus values — used to validate the ?category= search param. */
export const RECOVERY_STATUSES: readonly RecoveryStatus[] = [
  "QUEUED",
  "SCHEDULED",
  "PROCESSING",
  "RECOVERED",
  "HALTED",
  "NEEDS_ACTION",
];

/** Audit trail category filters, in display order. */
export const AUDIT_CATEGORIES = ["ALL", "AI_DECISION", "POLICY", "EXECUTION", "RESULT"] as const;

const AUDIT_CATEGORY_LABELS: Record<string, string> = {
  ALL: "All",
  AI_DECISION: "AI Decision",
  POLICY: "Policy",
  EXECUTION: "Execution",
  RESULT: "Result",
};

export function auditCategoryLabel(c: string): string {
  return AUDIT_CATEGORY_LABELS[c] ?? c;
}
