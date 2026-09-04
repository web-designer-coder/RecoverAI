import { useEffect, useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { toast } from "sonner";
import {
  ArrowLeft,
  Ban,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Copy,
  Mail,
  Phone,
  Play,
  RefreshCw,
  SearchX,
  ShieldAlert,
  ShieldCheck,
  User,
  XCircle,
} from "lucide-react";
import {
  analyzeRecovery,
  evaluatePolicyChecks,
  executeRecovery,
  getAudit,
  getRecovery,
  stopRecovery,
  subscribeStore,
  type PolicyCheck,
} from "@/lib/api";
import type { AuditEvent, RecoveryPaymentDetail } from "@/lib/types";
import {
  ACTION_LABELS,
  FAILURE_LABELS,
  METHOD_LABELS,
  formatDateTime,
  formatINR,
  formatPct,
} from "@/lib/format";
import { PriorityDot, StatusChip, CountUp, WorkspaceGroup, MetaLine, MetricBlock, Divider } from "@/components/primitives";
import { EmptyState, PageLoading } from "@/components/states";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app/recovery/$id")({
  head: () => ({
    meta: [
      { title: "Payment Recovery Detail — RecoverAI" },
      { name: "description", content: "AI diagnosis, prediction, policy checks and audit trail for a failed payment." },
      { property: "og:title", content: "Payment Recovery Detail — RecoverAI" },
      { property: "og:description", content: "Full decision trail for a single at-risk payment." },
    ],
  }),
  component: RecoveryDetail,
});

type ExecutePhase = "review" | "verifying" | "scheduling" | "done";

function RecoveryDetail() {
  const { id } = Route.useParams();
  const [payment, setPayment] = useState<RecoveryPaymentDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [phase, setPhase] = useState<ExecutePhase>("review");
  const [stopConfirmOpen, setStopConfirmOpen] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () => {
      getRecovery(id)
        .then((p) => {
          if (!alive) return;
          if (p === null && !notFound) setNotFound(true);
          setPayment(p);
        })
        .catch((err) => {
          console.error('Failed to load payment:', err);
          if (alive) setNotFound(true);
        });
      getAudit()
        .then((rows) => alive && setEvents(rows.filter((e) => e.payment_id === id)))
        .catch((err) => {
          console.error('Failed to load audit events:', err);
        });
    };
    load();
    const unsub = subscribeStore(load);
    return () => {
      alive = false;
      unsub();
    };
  }, [id, notFound]);

  const checks = useMemo(() => (payment ? evaluatePolicyChecks(payment) : []), [payment]);
  const hardFails = checks.filter((c) => c.kind === "fail");
  const escalations = checks.filter((c) => c.kind === "escalate");
  const approved = hardFails.length === 0 && escalations.length === 0;

  const run = async (kind: string, fn: () => Promise<unknown>) => {
    setBusy(kind);
    try {
      await fn();
      toast.success(kind === "analyze" ? "Re-analysis complete" : "Action completed");
      // Refresh data after re-analysis so updated predictions appear immediately
      if (kind === "analyze") {
        getRecovery(id).then((p) => { if (p) setPayment(p); }).catch(() => {});
        getAudit().then((rows) => setEvents(rows.filter((e) => e.payment_id === id))).catch(() => {});
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Something went wrong";
      toast.error(kind === "analyze" ? "Re-analysis failed" : "Action failed", { description: msg });
    } finally {
      setBusy(null);
    }
  };

  /** Review → Verifying Policy → Scheduling → Scheduled. */
  const confirmExecution = async () => {
    setPhase("verifying");
    // Brief pause for visual transition
    await new Promise((r) => setTimeout(r, 400));
    try {
      await executeRecovery(id);
      setPhase("scheduling");
      await new Promise((r) => setTimeout(r, 500));
      setPhase("done");
      toast.success("Recovery scheduled", { description: "Queued for optimal window execution." });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Execution failed";
      setPhase("review");
      toast.error("Recovery failed", { description: msg });
    }
  };

  if (notFound) {
    return (
      <EmptyState
        icon={SearchX}
        title="Payment not found"
        copy={`No recovery record exists for "${id}". It may have been settled outside the recovery window or the ID is incorrect.`}
        action={
          <Link to="/app/recovery" className="btn-primary !py-2">
            Back to Recovery Queue
          </Link>
        }
      />
    );
  }

  if (!payment) return <PageLoading label="Loading payment…" />;

  // Deterministic prediction curve around the optimal window.
  const base = Math.round(payment.recovery_probability * 100);
  const clamp = (n: number) => Math.min(95, Math.max(4, n));
  const optimalTime = payment.next_action_at ? new Date(payment.next_action_at) : null;
  const plusDays = (d: Date, days: number) =>
    new Date(d.getTime() + days * 24 * 3600_000).toISOString();
  const windows = [
    { label: "Now", time: "immediate retry", rate: clamp(base - 18), optimal: false },
    { label: "+12H", time: optimalTime ? formatDateTime(plusDays(optimalTime, -0.5)) : "—", rate: clamp(base - 8), optimal: false },
    {
      label: "Optimal",
      time: payment.next_action_at ? formatDateTime(payment.next_action_at) : "—",
      rate: base,
      optimal: true,
    },
    {
      label: "+2D",
      time: optimalTime ? formatDateTime(plusDays(optimalTime, 2)) : "—",
      rate: clamp(base - 14),
      optimal: false,
    },
  ];

  // Concise decision evidence — derived from domain fields only.
  const signals = [
    `${payment.retry_count} previous ${payment.retry_count === 1 ? "retry" : "retries"} on this charge`,
    `${FAILURE_LABELS[payment.failure_category]} classified as ${
      payment.failure_category === "INSUFFICIENT_FUNDS" || payment.failure_category === "NETWORK_FAILURE"
        ? "transient"
        : payment.failure_category === "BANK_DECLINE"
          ? "persistent"
          : "data-related"
    }`,
    `${METHOD_LABELS[payment.payment_method] ?? payment.payment_method} channel with historical recoverability`,
    `Failed ${formatDateTime(payment.failed_at)} — timing evaluated against settlement patterns`,
  ];

  const executionLocked =
    payment.status === "RECOVERED" ||
    payment.status === "HALTED" ||
    payment.recommended_action === "STOP" ||
    !approved;

  // Customer & Gateway copy helper
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      toast.success("Copied to clipboard");
    }).catch(() => {
      toast.error("Failed to copy");
    });
  };

  const facts: [string, string][] = [
    ["Customer", payment.customer_name || payment.customer_id],
    ["Amount", formatINR(payment.amount)],
    ["Currency", payment.currency],
    ["Method", METHOD_LABELS[payment.payment_method] ?? payment.payment_method],
    ["Failure Category", FAILURE_LABELS[payment.failure_category] ?? payment.failure_category],
    ["Created", formatDateTime(payment.created_at)],
    ["Failed At", formatDateTime(payment.failed_at)],
    ["Retries Used", String(payment.retry_count)],
    ["Provider Order", payment.provider_order_id || "—"],
    ["Provider Status", payment.provider_status || "—"],
  ];

  return (
    <div className="space-y-6">
      <Link to="/app/recovery" className="inline-flex items-center gap-2 text-[0.8125rem] text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Recovery Queue
      </Link>

      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label-sm inline-flex items-center gap-2 text-foreground">
            <PriorityDot priority={payment.priority} />
            Payment
          </p>
          <h1 className="num headline-md mt-2 text-foreground">{payment.payment_id}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StatusChip status={payment.status} />
          <button
            className="btn-ghost !py-2"
            disabled={busy !== null}
            aria-busy={busy === "analyze"}
            onClick={() => run("analyze", () => analyzeRecovery(id))}
          >
            <RefreshCw className={cn("h-4 w-4", busy === "analyze" && "animate-spin")} aria-hidden="true" />
            Re-analyze
          </button>
          <button
            className="btn-primary !py-2"
            disabled={executionLocked || busy !== null}
            aria-busy={busy === "schedule"}
            onClick={() => {
              setPhase("review");
              setModalOpen(true);
            }}
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            Review &amp; Schedule
          </button>
          <button
            className="btn-ghost !py-2"
            disabled={busy !== null || payment.status === "HALTED"}
            aria-busy={busy === "stop"}
            onClick={() => setStopConfirmOpen(true)}
          >
            <Ban className="h-4 w-4" aria-hidden="true" />
            Stop
          </button>
        </div>
      </header>

      {!approved && (
        <div className="flex items-start gap-3 rounded-lg border border-warning/20 bg-warning/[0.06] px-4 py-3 text-[0.8125rem] text-warning">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            Policy validation has not passed for this payment. Execution is locked until the blocking
            checks are resolved or an operator approves an exception.
          </p>
        </div>
      )}

      <WorkspaceGroup label="Customer & Gateway" title="Customer & Gateway Intelligence" description="Customer profile, gateway status, and payment summary details">
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* Customer Profile */}
          <div className="space-y-2.5 border-b border-border pb-4 lg:border-b-0 lg:pb-0">
            <p className="text-[0.75rem] font-medium text-muted-foreground uppercase tracking-wider">Customer Profile</p>
            <div className="flex items-center gap-2 text-[0.8125rem]">
              <User className="h-4 w-4 text-foreground shrink-0" aria-hidden="true" />
              <span className="font-medium text-foreground">{payment.customer_name || "—"}</span>
            </div>
            {payment.customer_email && (
              <div className="flex items-center gap-2 text-[0.8125rem]">
                <Mail className="h-4 w-4 text-foreground shrink-0" aria-hidden="true" />
                <span className="text-muted-foreground truncate max-w-[200px]">{payment.customer_email}</span>
                <button
                  onClick={() => copyToClipboard(payment.customer_email!)}
                  className="text-faint hover:text-foreground transition-colors"
                  aria-label="Copy email"
                >
                  <Copy className="h-3 w-3" aria-hidden="true" />
                </button>
              </div>
            )}
            {payment.customer_phone && (
              <div className="flex items-center gap-2 text-[0.8125rem]">
                <Phone className="h-4 w-4 text-foreground shrink-0" aria-hidden="true" />
                <span className="text-muted-foreground">{payment.customer_phone}</span>
                <button
                  onClick={() => copyToClipboard(payment.customer_phone!)}
                  className="text-faint hover:text-foreground transition-colors"
                  aria-label="Copy phone"
                >
                  <Copy className="h-3 w-3" aria-hidden="true" />
                </button>
              </div>
            )}
            <div className="flex items-center gap-2 text-[0.75rem] text-faint">
              <span>ID:</span>
              <span className="num font-medium text-muted-foreground">{payment.customer_id}</span>
              <button
                onClick={() => copyToClipboard(payment.customer_id)}
                className="text-faint hover:text-foreground transition-colors"
                aria-label="Copy customer ID"
              >
                <Copy className="h-3 w-3" aria-hidden="true" />
              </button>
            </div>
          </div>

          {/* Gateway Status */}
          <div className="space-y-2.5 border-b border-border pb-4 lg:border-b-0 lg:pb-0">
            <p className="text-[0.75rem] font-medium text-muted-foreground uppercase tracking-wider">Gateway Status</p>
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-4 text-[0.8125rem]">
                <span className="text-muted-foreground">Order ID</span>
                <span className="num font-medium text-foreground flex items-center gap-2">
                  {payment.provider_order_id || "—"}
                  {payment.provider_order_id && (
                    <button
                      onClick={() => copyToClipboard(payment.provider_order_id!)}
                      className="text-faint hover:text-foreground transition-colors"
                      aria-label="Copy order ID"
                    >
                      <Copy className="h-3 w-3" aria-hidden="true" />
                    </button>
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between gap-4 text-[0.8125rem]">
                <span className="text-muted-foreground">Status</span>
                <span className={cn(
                  "px-2 py-0.5 rounded text-[0.75rem] font-medium",
                  payment.provider_status === "captured" ? "bg-success/10 text-success" :
                  payment.provider_status === "failed" ? "bg-error/10 text-error" :
                  "bg-white/[0.06] text-muted-foreground"
                )}>
                  {payment.provider_status || "Unknown"}
                </span>
              </div>
            </div>
          </div>

          {/* Payment Summary */}
          <div className="space-y-2.5">
            <p className="text-[0.75rem] font-medium text-muted-foreground uppercase tracking-wider">Payment Summary</p>
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-4 text-[0.8125rem]">
                <span className="text-muted-foreground">Amount</span>
                <span className="num font-semibold text-foreground">{formatINR(payment.amount)}</span>
              </div>
              <div className="flex items-center justify-between gap-4 text-[0.8125rem]">
                <span className="text-muted-foreground">Method</span>
                <span className="font-medium text-foreground">{METHOD_LABELS[payment.payment_method]}</span>
              </div>
              <div className="flex items-center justify-between gap-4 text-[0.8125rem]">
                <span className="text-muted-foreground">Retry Count</span>
                <span className="num font-medium text-foreground">{payment.retry_count}</span>
              </div>
            </div>
          </div>
        </div>
      </WorkspaceGroup>

      {/* row 1 — overview / diagnosis+prediction / recommendation */}
      <div className="grid gap-6 xl:grid-cols-3">
        <WorkspaceGroup label="Payment Details" title="Payment Overview" description="Core payment fields and current status">
          <dl className="mt-4 space-y-3 text-[0.8125rem]">
            {facts.map(([k, v]) => (
              <div key={k} className="flex items-start justify-between gap-4 border-b border-border pb-3 last:border-0">
                <dt className="text-muted-foreground">{k}</dt>
                <dd className="num text-right text-foreground">{v}</dd>
              </div>
            ))}
            <div className="flex items-center justify-between border-t border-border pt-3">
              <dt className="text-muted-foreground">Status</dt>
              <dd>
                <StatusChip status={payment.status} />
              </dd>
            </div>
          </dl>
        </WorkspaceGroup>

        <section className="rounded-xl bg-white/[0.03] p-6" aria-label="AI diagnosis and recovery prediction">
          <p className="label-sm inline-flex items-center gap-2 text-foreground">
            <BrainCircuit className="h-3.5 w-3.5" aria-hidden="true" />
            AI Diagnosis
          </p>
          <div className="mt-4 flex items-baseline justify-between">
            <p className="font-display text-xl font-semibold text-foreground">{FAILURE_LABELS[payment.failure_category]}</p>
            <p className="num text-[0.8125rem] font-semibold text-foreground"><CountUp value={payment.confidence * 100} format={(n) => formatPct(n)} /> confidence</p>
          </div>

          {/* AI Explanation */}
          {payment.decision?.explanation && (
            <div className="mt-4 rounded-lg border border-ai/20 bg-ai/[0.04] p-4">
              <p className="text-[0.8125rem] leading-relaxed text-muted-foreground italic">
                "{payment.decision.explanation}"
              </p>
            </div>
          )}

          {/* Data Sufficiency Badge */}
          {payment.decision?.data_sufficiency && (
            <div className="mt-3 flex items-center gap-2">
              <span className="text-[0.75rem] text-muted-foreground">Data Sufficiency:</span>
              <span className={cn(
                "px-2 py-0.5 rounded text-[0.75rem] font-medium",
                payment.decision.data_sufficiency === "HIGH" ? "bg-success/10 text-success" :
                payment.decision.data_sufficiency === "MEDIUM" ? "bg-warning/10 text-warning" :
                "bg-error/10 text-error"
              )}>
                {payment.decision.data_sufficiency}
              </span>
            </div>
          )}

          {/* AI Signals Breakdown */}
          {payment.decision?.signals && payment.decision.signals.length > 0 && (
            <div className="mt-4">
              <p className="text-[0.75rem] font-medium text-muted-foreground uppercase tracking-wider mb-2">Signal Breakdown</p>
              <div className="space-y-2">
                {payment.decision.signals.map((signal, idx) => (
                  <div key={idx} className="flex items-start justify-between gap-3 border-b border-border pb-2 last:border-0">
                    <div className="min-w-0">
                      <p className="text-[0.8125rem] font-medium text-foreground">{signal.name}</p>
                      <p className="text-[0.75rem] text-muted-foreground truncate">{signal.value}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={cn(
                        "px-1.5 py-0.5 rounded text-[0.6875rem] font-medium",
                        signal.category === "POSITIVE" ? "bg-success/10 text-success" :
                        signal.category === "NEGATIVE" ? "bg-error/10 text-error" :
                        "bg-white/[0.06] text-muted-foreground"
                      )}>
                        {signal.impact}
                      </span>
                      <span className={cn(
                        "text-[0.6875rem] font-medium px-1.5 py-0.5 rounded",
                        signal.category === "POSITIVE" ? "text-success" :
                        signal.category === "NEGATIVE" ? "text-error" :
                        "text-muted-foreground"
                      )}>
                        {signal.category}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Legacy Signals (fallback when no structured signals) */}
          {(!payment.decision?.signals || payment.decision.signals.length === 0) && (
            <ul className="mt-4 space-y-2 border-t border-border pt-4">
              {signals.map((s) => (
                <li key={s} className="flex items-start gap-2 text-[0.8125rem] text-muted-foreground">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-faint" aria-hidden="true" />
                  {s}
                </li>
              ))}
            </ul>
          )}

          <p className="label-sm mt-6 text-faint">Recovery Prediction by Window</p>
          <div className="mt-3 grid grid-cols-4 gap-2">
            {windows.map((w) => (
              <div
                key={w.label}
                className={cn(
                  "rounded-lg border px-2 py-2.5 text-center",
                  w.optimal ? "border-ai/30 bg-ai/[0.08]" : "border-border bg-white/[0.03]",
                )}
              >
                <p className={cn("num text-base font-semibold", w.optimal ? "text-foreground" : "text-muted-foreground")}>
                  <CountUp value={w.rate} format={(n) => `${n}%`} />
                </p>
                <p className="label-sm mt-1 text-[0.5625rem] text-faint">{w.label}</p>
              </div>
            ))}
          </div>
          <p className="mt-3 inline-flex items-center gap-1.5 text-[0.75rem] text-muted-foreground">
            <Clock3 className="h-3.5 w-3.5 text-foreground" aria-hidden="true" />
            Optimal window:{" "}
            <span className="num font-medium text-foreground">
              {payment.next_action_at ? formatDateTime(payment.next_action_at) : "—"}
            </span>
          </p>
        </section>

        <section className="rounded-xl bg-white/[0.03] p-6" aria-label="Recommended action">
          <p className="label-sm text-faint">Recommendation</p>
          <p className="mt-4 font-display text-2xl font-bold tracking-tight text-foreground">
            {ACTION_LABELS[payment.recommended_action]}
          </p>
          <dl className="mt-5 space-y-3 border-t border-border pt-4 text-[0.8125rem]">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Expected Recovery</dt>
              <dd className="num font-semibold text-success"><CountUp value={payment.expected_recovery} format={formatINR} /></dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">Optimal Window</dt>
              <dd className="num text-right text-foreground">
                {payment.next_action_at ? formatDateTime(payment.next_action_at) : "—"}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Recovery Probability</dt>
              <dd className="num font-semibold text-foreground"><CountUp value={base} format={(n) => formatPct(n)} /></dd>
            </div>
          </dl>
          {payment.recommended_action === "STOP" && (
            <p className="mt-4 rounded-lg border border-error/20 bg-error/[0.06] px-3 py-2 text-[0.75rem] text-error">
              Non-retryable failure — recovery permanently halted per policy.
            </p>
          )}
          {payment.recommended_action === "ESCALATE" && (
            <p className="mt-4 rounded-lg border border-warning/20 bg-warning/[0.06] px-3 py-2 text-[0.75rem] text-warning">
              Escalation required — routed to operator review before any action.
            </p>
          )}
        </section>
      </div>

      {/* policy validation */}
      <section className="rounded-xl bg-white/[0.03] p-6" aria-label="Policy validation">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="label-sm text-faint">Policy Validation</p>
          <span className={`chip ${approved ? "chip-success" : escalations.length > 0 ? "chip-warning" : "chip-error"}`}>
            {approved ? (
              <ShieldCheck className="h-3 w-3" aria-hidden="true" />
            ) : (
              <ShieldAlert className="h-3 w-3" aria-hidden="true" />
            )}
            {approved ? "APPROVED" : escalations.length > 0 ? "ESCALATION REQUIRED" : "POLICY BLOCKED"}
          </span>
        </div>
        <ul className="mt-5 grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
          {checks.map((c) => (
            <PolicyCheckRow key={c.label} check={c} />
          ))}
        </ul>
      </section>

      {/* audit trail */}
      <section className="rounded-xl bg-white/[0.03] p-6" aria-label="Audit trail">
        <p className="label-sm text-faint">Action Timeline</p>
        <ol className="mt-6 space-y-0">
          {events.map((e, idx) => {
            // Pick icon based on event type
            const getEventIcon = (type: string) => {
              if (type.includes("PAYMENT_FAILED")) return <XCircle className="h-4 w-4 text-error" />;
              if (type.includes("AI_DIAGNOSIS")) return <BrainCircuit className="h-4 w-4 text-foreground" />;
              if (type.includes("POLICY_CHECK")) return <ShieldCheck className="h-4 w-4 text-warning" />;
              if (type.includes("ACTION_SELECTED") || type.includes("RECOVERY_SCHEDULED")) return <Play className="h-4 w-4 text-foreground" />;
              if (type.includes("RECOVERY_EXECUTED")) return <CheckCircle2 className="h-4 w-4 text-success" />;
              if (type.includes("RECOVERY_HALTED")) return <Ban className="h-4 w-4 text-error" />;
              if (type.includes("CUSTOMER_NOTIFIED")) return <Mail className="h-4 w-4 text-foreground" />;
              if (type.includes("PAYMENT_RECOVERED")) return <CheckCircle2 className="h-4 w-4 text-success" />;
              return <CheckCircle2 className="h-4 w-4 text-muted-foreground" />;
            };

            return (
              <li key={e.id} className="relative pl-8 pb-6 last:pb-0">
                {/* Connector line */}
                {idx < events.length - 1 && (
                  <div className="absolute left-3.5 top-5 bottom-0 w-px bg-border" aria-hidden="true" />
                )}
                {/* Icon */}
                <div className="absolute left-0 top-0.5 rounded-full bg-background p-0.5 border border-border">
                  {getEventIcon(e.type)}
                </div>
                {/* Content */}
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-[0.8125rem] font-medium text-foreground">{e.summary}</p>
                  <p className="num text-[0.75rem] text-faint">{formatDateTime(e.timestamp)}</p>
                </div>
                <p className="label-sm mt-1 text-muted-foreground">
                  {e.type.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, c => c.toUpperCase())}
                </p>
                {Object.keys(e.detail).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {Object.entries(e.detail).map(([k, v]) => (
                      <span key={k} className="inline-flex items-center gap-1 rounded bg-white/[0.04] px-2 py-1 text-[0.6875rem] text-muted-foreground">
                        <span className="text-faint">{k}:</span>
                        <span className="font-medium">{v}</span>
                      </span>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
          {events.length === 0 && (
            <li className="text-[0.8125rem] text-muted-foreground pl-8">
              No events recorded for this payment yet — actions will appear here as they happen.
            </li>
          )}
        </ol>
      </section>

      {/* stop confirmation dialog */}
      <Dialog open={stopConfirmOpen} onOpenChange={setStopConfirmOpen}>
        <DialogContent className="max-w-md gap-5 rounded-xl p-6">
          <DialogHeader>
            <DialogTitle>Stop Recovery?</DialogTitle>
            <DialogDescription>
              This permanently halts all recovery attempts for {payment.payment_id}. The payment will not be retried.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <button className="btn-ghost" onClick={() => setStopConfirmOpen(false)}>
              Cancel
            </button>
            <button
              className="btn-primary !bg-error hover:!bg-error/90"
              onClick={() => {
                setStopConfirmOpen(false);
                run("stop", () => stopRecovery(id));
              }}
            >
              <Ban className="h-4 w-4" aria-hidden="true" />
              Stop Recovery
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* confirmation modal */}
      <Dialog open={modalOpen} onOpenChange={(o) => phase !== "verifying" && phase !== "scheduling" && setModalOpen(o)}>
        <DialogContent className="max-w-md gap-5 rounded-xl p-6 animate-in fade-in zoom-in-95 slide-in-from-bottom-2 duration-300 ease-out">
          <DialogHeader>
            <DialogTitle>Schedule Recovery?</DialogTitle>
            <DialogDescription>
              The bounded action below will be queued for execution at the optimal window.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-2 gap-x-6 gap-y-4 rounded-lg border border-border bg-surface-low p-4 text-[0.8125rem]">
            <div>
              <p className="label-sm text-faint">Payment</p>
              <p className="num mt-1 font-medium text-foreground">{payment.payment_id}</p>
              <p className="num mt-0.5 font-semibold text-foreground">{formatINR(payment.amount)}</p>
            </div>
            <div>
              <p className="label-sm text-faint">Recommended Action</p>
              <p className="mt-1 font-medium text-foreground">{ACTION_LABELS[payment.recommended_action]}</p>
              <p className="num mt-0.5 text-foreground">{formatPct(base)} probability</p>
            </div>
            <div>
              <p className="label-sm text-faint">Optimal Window</p>
              <p className="num mt-1 text-foreground">
                {payment.next_action_at ? formatDateTime(payment.next_action_at) : "—"}
              </p>
            </div>
            <div>
              <p className="label-sm text-faint">Policy</p>
              <p
                className={cn(
                  "mt-1 inline-flex items-center gap-1.5 font-medium",
                  approved ? "text-success" : escalations.length > 0 ? "text-warning" : "text-error",
                )}
              >
                {approved ? (
                  <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {approved ? "APPROVED" : escalations.length > 0 ? "ESCALATION REQUIRED" : "BLOCKED"}
              </p>
            </div>
          </div>

          {(hardFails.length > 0 || escalations.length > 0) && (
            <div
              className={cn(
                "rounded-lg border px-3 py-2.5 text-[0.8125rem]",
                escalations.length > 0 && hardFails.length === 0
                  ? "border-warning/20 bg-warning/[0.06] text-warning"
                  : "border-error/20 bg-error/[0.06] text-error",
              )}
              role="alert"
            >
              <p className="font-semibold">
                {escalations.length > 0 && hardFails.length === 0
                  ? "ESCALATION REQUIRED"
                  : "POLICY BLOCKED"}
              </p>
              <p className="mt-1 text-[0.75rem]">
                {(escalations.length > 0 ? escalations : hardFails)
                  .map((c) => `${c.label}: ${c.detail}`)
                  .join(" · ")}
                {escalations.length > 0 && hardFails.length === 0 &&
                  " — awaiting operator approval; automatic execution is locked."}
              </p>
            </div>
          )}

          {phase !== "review" && phase !== "done" && (
            <div className="animate-in fade-in slide-in-from-top-2 duration-200 ease-out flex items-center gap-3 rounded-lg border border-border bg-surface-low px-3 py-2.5 text-[0.8125rem]">
              <RefreshCw className="h-4 w-4 animate-spin text-foreground" aria-hidden="true" />
              {phase === "verifying" ? "Verifying policy…" : "Scheduling recovery…"}
            </div>
          )}

          {phase === "done" && (
            <div className="animate-in fade-in slide-in-from-top-2 duration-200 ease-out flex items-center gap-3 rounded-lg border border-success/20 bg-success/[0.06] px-3 py-2.5 text-[0.8125rem] text-success">
              <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
              Recovery scheduled — processing through Razorpay. Status updates live on this page.
            </div>
          )}

          <DialogFooter>
            <button
              className="btn-ghost"
              onClick={() => setModalOpen(false)}
              disabled={phase === "verifying" || phase === "scheduling"}
            >
              Cancel
            </button>
            <button
              className="btn-primary"
              onClick={confirmExecution}
              disabled={!approved || phase !== "review"}
              aria-busy={phase === "verifying" || phase === "scheduling"}
            >
              {phase === "verifying" || phase === "scheduling" ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" aria-hidden="true" />
                  {phase === "verifying" ? "Verifying…" : "Scheduling…"}
                </>
              ) : phase === "done" ? (
                "Scheduled ✓"
              ) : (
                "Confirm Recovery"
              )}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PolicyCheckRow({ check }: { check: PolicyCheck }) {
  const Icon = check.kind === "pass" ? CheckCircle2 : check.kind === "escalate" ? ShieldAlert : XCircle;
  const tone =
    check.kind === "pass"
      ? "text-success"
      : check.kind === "escalate"
        ? "text-warning"
        : "text-error";
  return (
    <li className="flex items-start gap-2.5">
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", tone)} aria-hidden="true" />
      <div className="min-w-0">
        <p className="flex items-center gap-2 text-[0.8125rem] font-medium text-foreground">
          {check.label}
          <span className={cn("label-sm text-[0.5625rem]", tone)}>
            {check.kind === "pass" ? "PASS" : check.kind === "escalate" ? "ESCALATE" : "FAIL"}
          </span>
        </p>
        <p className="num mt-0.5 text-[0.75rem] text-muted-foreground">{check.detail}</p>
      </div>
    </li>
  );
}
