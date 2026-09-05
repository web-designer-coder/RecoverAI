import { useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ArrowDownRight,
  BrainCircuit,
  Clock3,
  ShieldCheck,
  TrendingUp,
  Wallet,
  RotateCcw,
} from "lucide-react";
import {
  evaluatePolicyChecks,
  getDashboard,
  getRecoveries,
  subscribeStore,
} from "@/lib/api";
import { toast } from "sonner";
import type { DashboardData, RecoveryPayment } from "@/lib/types";
import { ACTION_LABELS, FAILURE_LABELS, formatDateTime, formatINR, formatLakh, formatPct } from "@/lib/format";
import { CountUp, MetricBlock, MetaLine, PriorityDot, StatusChip, WorkspaceGroup } from "@/components/primitives";
import { LineChart } from "@/components/charts";
import { PageLoading, EmptyState, ChartErrorBoundary } from "@/components/states";

export const Route = createFileRoute("/app/dashboard")({
  head: () => ({
    meta: [
      { title: "Recovery Overview — RecoverAI" },
      { name: "description", content: "Revenue at risk, recovered revenue and live recovery performance." },
      { property: "og:title", content: "Recovery Overview — RecoverAI" },
      { property: "og:description", content: "Track revenue at risk and AI-recovered revenue in real time." },
    ],
  }),
  component: DashboardPage,
});

function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [active, setActive] = useState<RecoveryPayment[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () => {
      getDashboard()
        .then((d) => alive && setData(d))
        .catch(() => alive && setError(true));
      getRecoveries()
        .then((rows) => {
          if (!alive) return;
          setActive(
            rows
              .filter((p) => p.status === "PROCESSING" || p.status === "SCHEDULED" || p.status === "QUEUED")
              .sort((a, b) => b.recovery_probability * b.amount - a.recovery_probability * a.amount),
          );
        })
        .catch(() => alive && setActive([]));
    };
    load();
    const unsub = subscribeStore(load);
    return () => {
      alive = false;
      unsub();
    };
  }, []);

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Couldn't load recovery data"
        copy="The recovery service didn't respond. Retry, or head back to the queue."
        action={
          <button
            className="btn-primary !py-2"
            onClick={() => {
              toast.info("Retrying…", { description: "Loading recovery data" });
              setError(false);
              setData(null);
              setActive(null);
            }}
          >
            <RotateCcw className="h-4 w-4 mr-2" aria-hidden="true" />
            Retry
          </button>
        }
      />
    );
  }

  if (!data || !active) return <PageLoading label="Loading overview…" />;

  const k = data.kpis;

  // Tier 1 — primary financial metrics, visually dominant.
  const primary = [
    { label: "Revenue at Risk", value: k.revenueAtRisk, fmt: formatLakh, icon: AlertTriangle, tone: "text-error", sub: `${k.paymentsAtRisk.toLocaleString("en-IN")} payments exposed` },
    { label: "Recovered Revenue", value: k.recoveredRevenue, fmt: formatLakh, icon: Wallet, tone: "text-success", sub: `${k.activeRecoveries.toLocaleString("en-IN")} recoveries in flight` },
    { label: "Recovery Rate", value: k.recoveryRate, fmt: (n: number) => formatPct(n, 1), icon: TrendingUp, tone: "text-ai", sub: "vs 53.0% static baseline" },
  ];

  // Tier 2 — operational metrics, compact.
  const secondary = [
    { label: "Incremental Revenue", value: `+${formatLakh(k.incrementalRevenue)}`, icon: TrendingUp, tone: "text-success" },
    { label: "Active Recoveries", value: k.activeRecoveries.toLocaleString("en-IN"), icon: Activity, tone: "text-foreground" },
    { label: "Payments at Risk", value: k.paymentsAtRisk.toLocaleString("en-IN"), icon: AlertTriangle, tone: "text-muted-foreground" },
  ];

  // Highest-value pending decision drives the AI decision panel.
  const decision =
    [...active]
      .filter((p) => p.status !== "RECOVERED")
      .sort((a, b) => b.expected_recovery - a.expected_recovery)[0] ?? null;
  const decisionApproved = decision ? evaluatePolicyChecks(decision).every((c) => c.passed) : false;

  const funnelNonCurrency = data.funnel.filter((f) => !f.isCurrency);
  const funnelMax = funnelNonCurrency.length > 0 ? Math.max(...funnelNonCurrency.map((f) => f.value)) : 0;
  const hasFunnelData = funnelNonCurrency.length > 0;
  const hasBreakdownData = data.failureBreakdown.length > 0;
  const hasAiVsStaticData = data.aiVsStatic.length > 0;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="headline-md text-foreground">Overview</h1>
          <p className="mt-1 text-[0.8125rem] text-muted-foreground">Revenue at risk and AI recovery performance</p>
        </div>
        <Link to="/app/recovery" className="btn-primary !py-2">
          Recovery Queue
          <ArrowRight className="h-4 w-4" />
        </Link>
      </header>

      {/* tier 1 — financial headline metrics */}
      <WorkspaceGroup label="Financial Overview" title="Key Performance Indicators" description="Primary metrics showing revenue impact and recovery performance">
        <div className="grid gap-4 md:grid-cols-3">
          {primary.map((m) => (
            <MetricBlock key={m.label} label={m.label} value={<CountUp value={m.value} format={m.fmt} />} sub={m.sub} tone={m.tone === "text-error" ? "error" : m.tone === "text-success" ? "success" : m.tone === "text-ai" ? "ai" : "default"} />
          ))}
        </div>
      </WorkspaceGroup>

      {/* tier 2 — operational strip */}
      <WorkspaceGroup label="Operational Metrics" title="Key Operational Statistics" description="Secondary metrics providing additional context on recovery operations">
        <div className="grid grid-cols-1 sm:grid-cols-3">
          {secondary.map((m, i) => (
            <div key={m.label} className={`${i > 0 ? "border-l border-border " : ""}animate-in fade-in slide-in-from-left-2 duration-300 ease-out`} style={{ animationDelay: (i * 50) + "ms" }}>
              <MetaLine label={m.label} value={<span className={`num text-base font-semibold ${m.tone}`}>{m.value}</span>} />
            </div>
          ))}
        </div>
      </WorkspaceGroup>

      {/* AI decision summary — command panel */}
      {decision && (
        <WorkspaceGroup label="AI DECISION PANEL" title="Next Best Action" description="Highest expected-value recovery currently in the queue" as="section" className="rounded-xl border border-border-strong p-6 sm:px-5 animate-in fade-in slide-in-from-bottom-2 duration-500 ease-out transition-all duration-300 hover:border-border">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="label-sm inline-flex items-center gap-2 text-muted-foreground">
                <BrainCircuit className="h-3.5 w-3.5 text-ai" aria-hidden="true" />
                Next Best Action
              </p>
              <p className="mt-1.5 text-[0.8125rem] text-muted-foreground">
                Highest expected-value recovery currently in the queue
              </p>
            </div>
            <span className={`chip ${decisionApproved ? "chip-success" : "chip-warning"} transition-all duration-200`}>
              <ShieldCheck className="h-3 w-3" aria-hidden="true" />
              {decisionApproved ? "Policy Approved" : "Policy Review"}
            </span>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-border pt-4 sm:grid-cols-3 xl:grid-cols-6">
            {[
              ["Payment", <span className="num text-[0.8125rem] font-medium text-foreground">{decision.payment_id}</span>],
              ["AI Confidence", <CountUp value={decision.confidence * 100} format={(n) => formatPct(n)} className="num text-[0.8125rem] font-semibold text-foreground" />],
              ["Recovery Probability", <CountUp value={decision.recovery_probability * 100} format={(n) => formatPct(n)} className="num text-[0.8125rem] font-semibold text-foreground" />],
              ["Expected Recovery", <CountUp value={decision.expected_recovery} format={formatINR} className="num text-[0.8125rem] font-semibold text-success" />],
              ["Recommended Action", <span className="text-[0.8125rem] font-medium text-foreground">{ACTION_LABELS[decision.recommended_action]}</span>],
              ["Optimal Window", <span className="num text-[0.75rem] text-muted-foreground">{decision.next_action_at ? formatDateTime(decision.next_action_at) : "—"}</span>],
            ].map(([label, node], i) => (
              <div key={i} className="transition-all duration-300 hover:translate-y-[-2px]">
                <p className="label-sm text-faint">{label}</p>
                <div className="mt-1">{node}</div>
              </div>
            ))}
          </div>
          <div className="mt-4 border-t border-border pt-3">
            <Link
              to="/app/recovery/$id"
              params={{ id: decision.payment_id }}
              className="inline-flex items-center gap-1.5 text-[0.8125rem] text-white hover:text-muted-foreground hover:underline transition-all duration-200 hover:gap-2"
            >
              Review this recovery
              <ArrowRight className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-1" aria-hidden="true" />
            </Link>
          </div>
        </WorkspaceGroup>
      )}

      {/* performance chart + failure breakdown */}
      <WorkspaceGroup label="Performance Analysis" title="Recovery Insights" description="Visual analytics showing recovery trends and failure patterns">
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <WorkspaceGroup label="Revenue Trends" title="Recovered Revenue vs Static Baseline" description="Comparison of AI recovery performance against static retry baseline">
              <ChartErrorBoundary>
                <LineChart
                  className="mt-5"
                  series={data.recoveredSeries.map((r) => r.recovered)}
                  baseline={data.recoveredSeries.map((r) => r.baseline)}
                  labels={data.recoveredSeries.map((r) => r.month)}
                />
              </ChartErrorBoundary>
            </WorkspaceGroup>
          </div>
          <div>
            <WorkspaceGroup label="Failure Analysis" title="Failure Breakdown" description="Distribution of failed payments by category">
              {hasBreakdownData ? (
                <>
                <p className="label-sm mt-4 text-[0.6875rem] text-faint">Select a category to filter the queue</p>
                <ul className="mt-4 space-y-2.5">
                {(() => {
                const maxAmount = data.failureBreakdown.length > 0 ? Math.max(...data.failureBreakdown.map((x) => x.amount)) : 0;
                return data.failureBreakdown.map((f, index) => (
                  <li key={f.category} className="animate-in fade-in slide-in-from-left-2 duration-300 ease-out" style={{ animationDelay: `${index * 50}ms` }}>
                    <Link
                      to="/app/recovery"
                      search={{ category: f.category }}
                      className="group block rounded-lg px-2 py-1.5 transition-all duration-200 hover:bg-white/[0.04] hover:pl-3"
                    >
                      <span className="flex items-baseline justify-between gap-3">
                        <span className="text-[0.8125rem] text-muted-foreground group-hover:text-muted-foreground">{f.label}</span>
                        <span className="num text-[0.8125rem] text-muted-foreground">
                          {formatLakh(f.amount)}
                          <span className="ml-2 text-faint">{f.count}</span>
                        </span>
                      </span>
                      <span className="mt-1.5 block h-1 overflow-hidden rounded-full bg-white/[0.06]">
                        <span
                          className="block h-full rounded-full bg-white/[0.12] transition-opacity group-hover:brightness-125"
                          style={{ width: maxAmount > 0 ? `${(f.amount / maxAmount) * 100}%` : "0%" }}
                        />
                      </span>
                    </Link>
                  </li>
                ));
              })()}
                </ul>
                </>
              ) : (
                <EmptyState
                  title="No failure data yet"
                  copy="Failure categories will appear here as payments fail."
                  className="py-8"
                />
              )}
            </WorkspaceGroup>
          </div>
        </div>
      </WorkspaceGroup>

      {/* funnel + AI vs static */}
      <WorkspaceGroup label="Recovery Analytics" title="Performance Analytics" description="Detailed breakdown of recovery performance across different dimensions">
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <WorkspaceGroup label="Recovery Funnel" title="Recovery Funnel" description="Payment flow stages showing conversion at each step">
              {hasFunnelData ? (
                <>
                <ol className="mt-4 space-y-3">
                  {data.funnel.map((f, i) =>
                    f.isCurrency ? null : (
                      <li key={f.label} className="animate-in fade-in slide-in-from-left-2 duration-300 ease-out" style={{ animationDelay: `${i * 80}ms` }}>
                        <div className="flex items-baseline justify-between">
                          <span className="text-[0.8125rem] text-muted-foreground">
                            <span className="num mr-2 text-[0.6875rem] text-faint">{String(i + 1).padStart(2, "0")}</span>
                            {f.label}
                          </span>
                          <span className="num text-[0.8125rem] font-semibold text-white">{f.value.toLocaleString("en-IN")}</span>
                        </div>
                        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                          <div
                            className={
                              i === 3
                                ? "h-full rounded-full bg-success"
                                : i === 0
                                  ? "h-full rounded-full bg-error/60"
                                  : "h-full rounded-full bg-white/[0.12]"
                            }
                            style={{ width: funnelMax > 0 ? `${(f.value / funnelMax) * 100}%` : "0%" }}
                          />
                        </div>
                        {i < 2 && <ArrowDownRight className="ml-1 mt-0.5 h-3 w-3 text-faint" aria-hidden="true" />}
                      </li>
                    ),
                  )}
                </ol>
                <div className="mt-3 flex items-center justify-between border-t border-border pt-3">
                  <span className="label-sm text-faint">Recovered Revenue</span>
                  <span className="num text-[0.8125rem] font-semibold text-success">
                    {formatINR(data.funnel.find((f) => f.isCurrency)?.value ?? 0)}
                  </span>
                </div>
                </>
              ) : (
                <EmptyState
                  title="No funnel data yet"
                  copy="Payment flow stages will appear as recoveries are processed."
                  className="py-8"
                />
              )}
            </WorkspaceGroup>
          </div>

          <div>
            <WorkspaceGroup label="AI Performance" title="AI vs Static Retries" description="Comparison of AI-powered recovery against static retry baseline">
              {hasAiVsStaticData ? (
                <>
                <table className="mt-4 w-full text-[0.8125rem]">
                  <thead>
                    <tr className="border-b border-border text-left">
                      {["Metric", "Static", "RecoverAI", "Lift"].map((h) => (
                        <th key={h} className="label-sm pb-2 text-faint">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.aiVsStatic.map((r, i) => (
                      <tr key={r.metric} className="border-b border-border last:border-0 animate-in fade-in slide-in-from-left-2 duration-300 ease-out" style={{ animationDelay: `${i * 60}ms` }}>
                        <td className="py-2.5 pr-2 text-muted-foreground">{r.metric}</td>
                        <td className="num py-2.5 pr-2 text-right text-faint">{r.static}</td>
                        <td className="num py-2.5 pr-2 text-right font-semibold text-white">{r.ai}</td>
                        <td className="num py-2.5 pr-2 text-right text-success">{r.delta}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="mt-3 inline-flex items-center gap-1.5 text-[0.6875rem] text-faint">
                  <Clock3 className="h-3.5 w-3.5" aria-hidden="true" />
                  Measured on the same payment population — values update as recoveries settle.
                </p>
                </>
              ) : (
                <EmptyState
                  title="No comparison data yet"
                  copy="AI vs Static performance metrics will populate as recoveries complete."
                  className="py-8"
                />
              )}
            </WorkspaceGroup>
          </div>
        </div>
      </WorkspaceGroup>

      {/* active recoveries */}
      <WorkspaceGroup label="Live Queue" title="Active Recoveries" description="Currently processing and queued payments awaiting action">
        <div className="flex items-center justify-between px-5 pb-2 pt-4">
          <p className="label-sm text-faint">Active Recoveries</p>
          <Link to="/app/recovery" className="text-[0.75rem] text-muted-foreground hover:text-foreground transition-colors">
            View full queue
          </Link>
        </div>
        {active.length === 0 ? (
          <EmptyState
            title="No active recoveries"
            copy="Every eligible payment has completed its recovery cycle. New failures appear here automatically."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-[0.8125rem]">
              <thead>
                <tr className="border-b border-border text-left">
                  {["Payment", "Customer", "Amount", "Probability", "Action", "Status"].map((h) => (
                    <th key={h} className="label-sm px-5 py-2.5 text-faint">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {active.slice(0, 6).map((p, i) => (
                  <tr key={p.payment_id} className="border-b border-border last:border-0 hover:bg-white/[0.03] transition-all duration-150 animate-in fade-in slide-in-from-left-2 duration-300 ease-out" style={{ animationDelay: `${i * 60}ms` }}>
                    <td className="px-5 py-3">
                      <Link to="/app/recovery/$id" params={{ id: p.payment_id }} className="flex items-center gap-2 transition-colors duration-150">
                        <PriorityDot priority={p.priority} />
                        <span className="num font-medium text-white hover:text-muted-foreground">{p.payment_id}</span>
                      </Link>
                    </td>
                    <td className="num px-5 py-3 text-muted-foreground">{p.customer_id}</td>
                    <td className="num px-5 py-3 text-white">{formatINR(p.amount)}</td>
                    <td className="num px-5 py-3 text-white">{formatPct(p.recovery_probability * 100)}</td>
                    <td className="px-5 py-3 text-muted-foreground">{ACTION_LABELS[p.recommended_action]}</td>
                    <td className="px-5 py-3">
                      <StatusChip status={p.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </WorkspaceGroup>
    </div>
  );
}
