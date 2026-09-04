import { useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronDown, Inbox } from "lucide-react";
import { getAudit, subscribeStore } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";
import { formatDateTime, formatINR } from "@/lib/format";
import { AUDIT_CATEGORIES, auditCategoryLabel } from "@/lib/constants";
import { EmptyState, Skeleton, ErrorState } from "@/components/states";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export const Route = createFileRoute("/app/audit")({
  head: () => ({
    meta: [
      { title: "Audit Trail — RecoverAI" },
      { name: "description", content: "Immutable log of AI decisions, policy checks and recovery executions." },
      { property: "og:title", content: "Audit Trail — RecoverAI" },
      { property: "og:description", content: "Every decision and action, fully reconstructable." },
    ],
  }),
  component: AuditPage,
});

function AuditPage() {
  const [rows, setRows] = useState<AuditEvent[] | null>(null);
  const [category, setCategory] = useState<string>("ALL");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      setError(null);
      getAudit(category)
        .then((r) => {
          if (alive) setRows(r);
        })
        .catch((err) => {
          console.error('Failed to load audit trail:', err);
          if (alive) {
            setRows([]);
            setError(err instanceof Error ? err.message : 'Failed to load audit trail');
          }
        });
    };
    load();
    const unsub = subscribeStore(load);
    return () => {
      alive = false;
      unsub();
    };
  }, [category]);

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="headline-md text-foreground">Audit Trail</h1>
          <p className="mt-1.5 text-[0.8125rem] text-muted-foreground">
            Chronological record of every AI decision, policy check and execution — newest first.
          </p>
        </div>
        <button
          className="btn-ghost !py-2"
          onClick={() => window.location.reload()}
          aria-label="Refresh audit trail"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M23 4v6h-6" />
            <path d="M1 20v-6h6" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
        </button>
      </header>

      <div className="flex flex-wrap gap-2">
        {AUDIT_CATEGORIES.map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            aria-pressed={category === c}
            className={`chip ${category === c ? "chip-neutral bg-white/[0.04]" : "chip-neutral"} transition-all duration-200 hover:scale-105 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background`}
          >
            {auditCategoryLabel(c)}
          </button>
        ))}
      </div>

      <div className="rounded-xl bg-white/[0.03] border border-border p-6 transition-all duration-300 hover:border-border/50 hover:shadow-[0_8px_30px_-10px_rgba(0,0,0,0.3)]">
        {error ? (
          <ErrorState
            title="Couldn't load the audit trail"
            copy={error}
            retry={() => {
              setError(null);
              setRows(null);
            }}
          />
        ) : rows === null ? (
          <div className="space-y-4" role="status" aria-live="polite">
            <Skeleton className="h-4 w-40" />
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="animate-in fade-in slide-in-from-top-2 duration-300 ease-out" style={{ animationDelay: `${i * 100}ms` }}>
                <div className="flex items-start gap-3 pl-7">
                  <Skeleton className="h-[19px] w-[19px] shrink-0 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-3 w-1/2" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={Inbox}
            title="No events in this category"
            copy="Events appear here the moment an AI decision is made or a recovery action runs. Try a different category filter."
            action={
              category !== "ALL" && (
                <button className="btn-ghost !py-2" onClick={() => setCategory("ALL")}>
                  Show all events
                </button>
              )
            }
          />
        ) : (
          <ol className="relative space-y-0" aria-label="Chronological audit timeline">
            {rows.map((e, i) => {
              const detailEntries = Object.entries(e.detail);
              const hasDetail = detailEntries.length > 0;
              const open = expanded.has(e.id);
              const categoryColor =
                e.category === "AI_DECISION"
                  ? "bg-ai"
                  : e.category === "POLICY"
                    ? "bg-warning"
                    : e.category === "EXECUTION"
                      ? "bg-foreground"
                      : e.category === "RESULT"
                        ? "bg-success"
                        : "bg-white/[0.2]";
              return (
                <li
                  key={e.id}
                  className="relative pb-6 pl-7 last:pb-0 animate-in fade-in slide-in-from-left-2 duration-300 ease-out"
                  style={{ animationDelay: `${i * 50}ms` }}
                >
                  {/* timeline rail */}
                  {i < rows.length - 1 && (
                    <span className="absolute bottom-0 left-[9px] top-6 w-px bg-white/[0.06]" aria-hidden="true" />
                  )}
                  <span className="absolute left-0 top-1 flex h-[19px] w-[19px] items-center justify-center rounded-full border border-border bg-surface-low transition-all duration-300" aria-hidden="true">
                    <span
                      className={cn("h-1.5 w-1.5 rounded-full transition-all duration-300", categoryColor, open && "scale-125")}
                    />
                  </span>

                  <div className="group flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 transition-colors duration-200">
                    <p className="text-[0.8125rem] font-medium text-foreground">{e.summary}</p>
                    <p className="num shrink-0 text-[0.75rem] text-faint">{formatDateTime(e.timestamp)}</p>
                  </div>

                  <div className="mt-1.5 flex flex-wrap items-center gap-2.5">
                    <span className="label-sm text-muted-foreground">{auditCategoryLabel(e.category)}</span>
                    {e.amount != null && (
                      <span className="num text-[0.75rem] font-medium text-foreground">{formatINR(e.amount)}</span>
                    )}
                    <Link
                      to="/app/recovery/$id"
                      params={{ id: e.payment_id }}
                      className="num text-[0.75rem] text-muted-foreground hover:text-foreground hover:underline transition-colors duration-150 inline-flex items-center gap-1"
                    >
                      {e.payment_id}
                      <svg className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity duration-150" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M5 12h14M12 5l7 7-7 7" />
                      </svg>
                    </Link>
                  </div>

                  {hasDetail && (
                    <div className="mt-1.5 animate-in fade-in slide-in-from-top-2 duration-200 ease-out">
                      <button
                        onClick={() => toggle(e.id)}
                        aria-expanded={open}
                        className="inline-flex items-center gap-1 text-[0.75rem] text-muted-foreground transition-colors hover:text-foreground hover:scale-105 active:scale-95"
                      >
                        <ChevronDown
                          className={cn("h-3 w-3 transition-transform duration-200", open && "rotate-180")}
                          aria-hidden="true"
                        />
                        {open ? "Hide details" : "Details"}
                      </button>
                      {open && (
                        <dl className="mt-2 grid gap-x-8 gap-y-2 rounded-lg border border-border bg-surface-low px-3.5 py-3 sm:grid-cols-2 lg:grid-cols-3 animate-in fade-in duration-200 ease-out">
                          {detailEntries.map(([k, v]) => (
                            <div key={k} className="transition-all duration-150 hover:bg-white/[0.03] rounded px-1 -mx-1">
                              <dt className="label-sm text-faint">{k}</dt>
                              <dd className="num mt-0.5 text-[0.75rem] text-foreground">{v}</dd>
                            </div>
                          ))}
                        </dl>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
