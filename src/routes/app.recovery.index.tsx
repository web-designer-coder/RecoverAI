import { useEffect, useRef, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Search, X, Inbox, Check, CheckSquare, Square, AlertTriangle, BrainCircuit, Ban } from "lucide-react";
import { getRecoveries, subscribeStore, analyzeRecovery, executeRecovery, stopRecovery } from "@/lib/api";
import { toast } from "sonner";
import type { FailureCategory, RecoveryPayment, RecoveryStatus } from "@/lib/types";
import { ACTION_LABELS, FAILURE_LABELS, formatDateTime, formatINR, formatPct } from "@/lib/format";
import { QUEUE_FILTERS, RECOVERY_STATUSES, queueFilterLabel } from "@/lib/constants";
import { PriorityDot, StatusChip, WorkspaceGroup } from "@/components/primitives";
import { EmptyState, ErrorState, Skeleton } from "@/components/states";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app/recovery/")({
  validateSearch: (search: Record<string, unknown>): { category?: FailureCategory; status?: RecoveryStatus } => {
    const next: { category?: FailureCategory; status?: RecoveryStatus } = {};
    const rawCategory = search["category"];
    if (typeof rawCategory === "string" && Object.keys(FAILURE_LABELS).includes(rawCategory)) {
      next.category = rawCategory as FailureCategory;
    }
    const rawStatus = search["status"];
    if (typeof rawStatus === "string" && RECOVERY_STATUSES.includes(rawStatus as RecoveryStatus)) {
      next.status = rawStatus as RecoveryStatus;
    }
    return next;
  },
  head: () => ({
    meta: [
      { title: "Recovery Queue — RecoverAI" },
      { name: "description", content: "Prioritised queue of failed payments with AI recovery recommendations." },
      { property: "og:title", content: "Recovery Queue — RecoverAI" },
      { property: "og:description", content: "Every at-risk payment, ranked by recovery value and probability." },
    ],
  }),
  component: RecoveryQueue,
});

function RecoveryQueue() {
  const { category, status } = Route.useSearch();
  const navigate = useNavigate();
  const [rows, setRows] = useState<RecoveryPayment[] | null>(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeStatus = status ?? "ALL";
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectAll, setSelectAll] = useState(false);

  // Check if all visible rows are selected
  const allSelected = rows && rows.length > 0 && selectedIds.size === rows.length;

  const toggleSelectAll = () => {
    if (allSelected || selectAll) {
      setSelectedIds(new Set());
      setSelectAll(false);
    } else if (rows) {
      setSelectedIds(new Set(rows.map((r) => r.payment_id)));
      setSelectAll(true);
    }
  };

  const toggleRow = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
    setSelectAll(false);
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
    setSelectAll(false);
  };

  // Debounce search input (~300ms) to avoid rapid API calls on each keystroke
  useEffect(() => {
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [search]);

  const runBulkAction = async (action: "analyze" | "schedule" | "stop", ids: string[]) => {
    if (ids.length === 0) return;
    toast.info(`${action.charAt(0).toUpperCase() + action.slice(1)}ing ${ids.length} payment${ids.length > 1 ? "s" : ""}…`);
    let success = 0;
    let failed = 0;
    for (const id of ids) {
      try {
        if (action === "analyze") {
          await analyzeRecovery(id);
        } else if (action === "schedule") {
          await executeRecovery(id);
        } else if (action === "stop") {
          await stopRecovery(id);
        }
        success++;
      } catch {
        failed++;
      }
    }
    if (success > 0) {
      toast.success(`${success} payment${success > 1 ? "s" : ""} ${action === "analyze" ? "re-analyzed" : action === "schedule" ? "scheduled" : "stopped"}`);
    }
    if (failed > 0) {
      toast.error(`${failed} payment${failed > 1 ? "s" : ""} failed to ${action}`);
    }
    clearSelection();
  };

  const [reloadTrigger, setReloadTrigger] = useState(0);

  useEffect(() => {
    let alive = true;
    const load = () => {
      setError(null);
      getRecoveries({
        status: activeStatus,
        ...(category ? { category } : {}),
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
      })
        .then((r) => {
          if (alive) setRows(r);
        })
        .catch((err) => {
          console.error('Failed to load recoveries:', err);
          if (alive) {
            setRows([]);
            setError(err instanceof Error ? err.message : 'Failed to load recovery queue');
            toast.error("Failed to load recovery queue", { description: err instanceof Error ? err.message : "Unknown error" });
          }
        });
    };
    load();
    const unsub = subscribeStore(load);
    return () => {
      alive = false;
      unsub();
    };
  }, [activeStatus, category, debouncedSearch, reloadTrigger]);

  const clearCategory = () => {
    navigate({ to: "/app/recovery", search: status ? { status } : {}, replace: true });
  };

  return (
    <div className="space-y-6">
      <WorkspaceGroup label="Recovery Queue" title="Prioritized Failed Payments" description="Every at-risk payment, ranked by recovery value and AI-assessed probability.">
        {/* WorkspaceGroup renders the page heading; duplicate below is intentionally removed */}
        <span className="sr-only">Page header</span>
      </WorkspaceGroup>

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1.5">
          {QUEUE_FILTERS.map((f) => (
            <button
              key={f}
              onClick={() =>
                navigate({
                  to: "/app/recovery",
                  search: f === "ALL" ? (category ? { category } : {}) : { status: f as RecoveryStatus },
                })
              }
              aria-pressed={activeStatus === f}
              className={`chip ${activeStatus === f ? "chip-neutral bg-white/[0.04]" : "chip-neutral"} transition-all duration-200 hover:scale-105 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background`}
            >
              {queueFilterLabel(f)}
            </button>
          ))}
        </div>
        <div className="relative ml-auto w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint transition-colors duration-200 group-focus-within:text-muted-foreground" aria-hidden="true" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search payment or customer"
            aria-label="Search payments by payment ID, customer ID or failure reason"
            className="input-field !pl-10 transition-all duration-200 hover:border-border/50 focus:ring-2 focus:ring-foreground/30 focus:border-foreground"
          />
        </div>
      </div>

      {category && (
        <div className="flex items-center gap-2">
          <span className="chip chip-neutral">
            Category · {FAILURE_LABELS[category]}
            <button onClick={clearCategory} aria-label="Clear category filter">
              <X className="ml-1 inline h-3 w-3 text-muted-foreground hover:text-error" />
            </button>
          </span>
        </div>
      )}

      {/* Bulk Action Toolbar */}
      {selectedIds.size > 0 && (
        <div className="animate-in fade-in slide-in-from-top-2 duration-200 ease-out rounded-xl border border-ai/20 bg-ai/[0.04] p-4" role="status" aria-live="polite">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="text-[0.8125rem] text-foreground">
                <strong>{selectedIds.size}</strong> payment{selectedIds.size > 1 ? "s" : ""} selected
              </span>
              <button
                className="btn-ghost !py-1.5 text-[0.75rem]"
                onClick={clearSelection}
              >
                <X className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
                Clear Selection
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="btn-primary !py-1.5 text-[0.75rem]"
                onClick={() => runBulkAction("analyze", Array.from(selectedIds))}
              >
                <BrainCircuit className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
                Re-analyze
              </button>
              <button
                className="btn-primary !py-1.5 text-[0.75rem]"
                onClick={() => runBulkAction("schedule", Array.from(selectedIds))}
              >
                <Check className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
                Schedule
              </button>
              <button
                className="btn-ghost !py-1.5 text-[0.75rem]"
                onClick={() => runBulkAction("stop", Array.from(selectedIds))}
              >
                <Ban className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
                Stop
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="rounded-xl bg-white/[0.03] border border-border overflow-hidden">
        {error ? (
          <ErrorState
            title="Couldn't load the recovery queue"
            copy={error}
            retry={() => {
              setError(null);
              setRows(null);
            }}
          />
        ) : rows === null ? (
          <div className="p-5 space-y-2.5" role="status" aria-live="polite">
            <Skeleton className="h-4 w-32" />
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-11 w-full" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={Inbox}
            title="No matching payments"
            copy={
              category
                ? `No ${(FAILURE_LABELS[category] ?? category).toLowerCase()} failures match this view. Clear the category filter or adjust your search.`
                : "No payments match the current filter or search. Try clearing the filters to see the full queue."
            }
            action={
              (category || activeStatus !== "ALL" || search) && (
                <button
                  className="btn-ghost !py-2"
                  onClick={() => {
                    setSearch("");
                    clearCategory();
                  }}
                >
                  Clear filters
                </button>
              )
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1040px] text-[0.8125rem]">
              <thead>
                <tr className="border-b border-border text-left">
                  <th className="label-sm px-5 py-2.5 w-10">
                    <button
                      onClick={toggleSelectAll}
                      aria-label={allSelected ? "Deselect all" : "Select all"}
                      aria-pressed={allSelected ? "true" : "false"}
                      className="inline-flex items-center justify-center transition-all duration-200 hover:scale-105 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded"
                    >
                      {allSelected ? (
                        <CheckSquare className="h-4 w-4 text-foreground" aria-hidden="true" />
                      ) : (
                        <Square className="h-4 w-4 text-faint hover:text-muted-foreground" aria-hidden="true" />
                      )}
                    </button>
                  </th>
                  {["Priority", "Payment", "Customer", "Amount", "Failure", "Probability", "Action", "Status", "Next Action"].map(
                    (h) => (
                      <th key={h} className="label-sm px-5 py-2.5 text-faint">
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const isSelected = selectedIds.has(p.payment_id);
                  return (
                    <tr
                      key={p.payment_id}
                      className={cn(
                        "cursor-pointer border-b border-border last:border-0 transition-colors duration-150",
                        isSelected ? "bg-ai/[0.06] hover:bg-ai/[0.08]" : "hover:bg-white/[0.03]"
                      )}
                      onClick={(e) => {
                        // Don't trigger row navigation when clicking checkbox cell
                        const target = e.target as HTMLElement;
                        if (target.closest('[data-checkbox-cell]')) return;
                        navigate({ to: "/app/recovery/$id", params: { id: p.payment_id } });
                      }}
                    >
                      <td data-checkbox-cell className="px-5 py-3 w-10" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => toggleRow(p.payment_id)}
                          aria-label={isSelected ? `Deselect ${p.payment_id}` : `Select ${p.payment_id}`}
                          aria-pressed={isSelected ? "true" : "false"}
                          className="inline-flex items-center justify-center transition-all duration-200 hover:scale-105 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded"
                        >
                          {isSelected ? (
                            <CheckSquare className="h-4 w-4 text-foreground" aria-hidden="true" />
                          ) : (
                            <Square className="h-4 w-4 text-faint hover:text-muted-foreground" aria-hidden="true" />
                          )}
                        </button>
                      </td>
                      <td className="px-5 py-3">
                        <PriorityDot priority={p.priority} />
                      </td>
                      <td className="num px-5 py-3 font-medium text-foreground">{p.payment_id}</td>
                      <td className="num px-5 py-3 text-muted-foreground">{p.customer_id}</td>
                      <td className="num px-5 py-3 text-foreground">{formatINR(p.amount)}</td>
                      <td className="max-w-[180px] truncate px-5 py-3 text-muted-foreground" title={p.failure_reason}>
                        {FAILURE_LABELS[p.failure_category]}
                      </td>
                      <td className="num px-5 py-3 text-foreground">{formatPct(p.recovery_probability * 100)}</td>
                      <td className="px-5 py-3 text-muted-foreground">{ACTION_LABELS[p.recommended_action]}</td>
                      <td className="px-5 py-3">
                        <StatusChip status={p.status} />
                      </td>
                      <td className="num px-5 py-3 text-[0.75rem] text-faint">
                        {p.next_action_at ? formatDateTime(p.next_action_at) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
