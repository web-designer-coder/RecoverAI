import { useEffect, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { AlertTriangle, CheckCircle2, Loader2, Play, RotateCcw, X, TrendingUp, Wallet } from "lucide-react";
import { runSimulation } from "@/lib/api";
import { toast } from "sonner";
import type { SimulationInput, SimulationResult } from "@/lib/types";
import { formatINR, formatLakh, formatPct } from "@/lib/format";
import { CompareBars } from "@/components/charts";
import { CountUp } from "@/components/primitives";
import { EmptyState } from "@/components/states";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app/simulator")({
  head: () => ({
    meta: [
      { title: "Recovery Simulator — RecoverAI" },
      { name: "description", content: "Batch-simulate recovery outcomes and compare AI against static retries." },
      { property: "og:title", content: "Recovery Simulator — RecoverAI" },
      { property: "og:description", content: "Prove incremental revenue before you switch anything on." },
    ],
  }),
  component: SimulatorPage,
});

const STAGES = [
  "Analyzing transactions",
  "Diagnosing failures",
  "Predicting recovery probability",
  "Selecting interventions",
  "Applying policy constraints",
  "Simulating recovery",
] as const;

/** ~400ms per stage keeps the whole pipeline inside the 2–3s budget. */
const STAGE_MS = 400;

function SimulatorPage() {
  const [input, setInput] = useState<SimulationInput>({
    transactions: 5000,
    avgTransactionAmount: 2400,
    failureRate: 0.12,
    recoveryWindowDays: 14,
  });
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [stage, setStage] = useState<number | null>(null); // null = idle
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Advance through the staged pipeline, then fetch the deterministic result.
  useEffect(() => {
    if (stage === null || stage > STAGES.length) return undefined;
    if (stage === STAGES.length) {
      let alive = true;
      runSimulation(input)
        .then((r) => {
          if (!alive) return;
          setResult(r);
          setStage(null);
          toast.success("Simulation complete", { description: "Results ready for review" });
        })
        .catch((err) => {
          console.error('Simulation failed:', err);
          if (alive) {
            setStage(null);
            const msg = err instanceof Error ? err.message : 'Simulation failed';
            setError(msg);
            toast.error("Simulation failed", { description: msg });
          }
        });
      return () => {
        alive = false;
      };
    }
    timer.current = setTimeout(() => setStage((s) => (s === null ? null : s + 1)), STAGE_MS);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
    // Inputs are locked while running, so they cannot change mid-pipeline.
  }, [stage, input]);

  const running = stage !== null;
  const complete = stage !== null && stage >= STAGES.length;

  const start = () => {
    setResult(null);
    setError(null);
    setStage(0);
    toast.info("Simulation started", { description: "Running pipeline stages…" });
  };

  const cancel = () => {
    if (timer.current) clearTimeout(timer.current);
    setStage(null);
    toast.info("Simulation cancelled");
  };

  const reset = () => {
    if (timer.current) clearTimeout(timer.current);
    setStage(null);
    setResult(null);
    setInput({
      transactions: 5000,
      avgTransactionAmount: 2400,
      failureRate: 0.12,
      recoveryWindowDays: 14,
    });
  };

  const isValidInput = () => {
    return input.transactions >= 100 &&
           input.avgTransactionAmount >= 100 &&
           input.failureRate >= 0.01 && input.failureRate <= 1 &&
           input.recoveryWindowDays >= 1;
  };

  const fields = [
    { key: "transactions", label: "Transactions", step: 100, min: 100 },
    { key: "avgTransactionAmount", label: "Avg Transaction (₹)", step: 100, min: 100 },
    { key: "failureRate", label: "Failure Rate (0–1)", step: 0.01, min: 0.01 },
    { key: "recoveryWindowDays", label: "Recovery Window (days)", step: 1, min: 1 },
  ] as const;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="headline-md text-foreground">Simulator</h1>
        <p className="mt-1.5 text-[0.8125rem] text-muted-foreground">
          Model recovery outcomes on your failure population before switching anything on.
        </p>
      </header>

      <div className="rounded-xl bg-white/[0.03] border border-border p-5">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 animate-in fade-in slide-in-from-top-2 duration-300 ease-out">
          {fields.map((f, i) => (
            <label key={f.key} className="block" style={{ animationDelay: `${i * 80}ms` }}>
              <span className="label-sm text-faint">{f.label}</span>
              <input
                type="number"
                step={f.step}
                min={f.min}
                value={input[f.key]}
                disabled={running}
                onChange={(e) =>
                  setInput((prev) => ({ ...prev, [f.key]: Number(e.target.value) }))
                }
                className="input-field num mt-2 w-full transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed hover:border-border/50 focus:ring-2 focus:ring-foreground/30 focus:border-foreground"
              />
            </label>
          ))}
        </div>
        <div className="mt-5 flex flex-wrap gap-3">
          {!running && result === null && !error && (
            <button
              className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={() => {
                if (!isValidInput()) {
                  toast.error("Invalid input", { description: "Please check all fields are within valid ranges" });
                  return;
                }
                start();
              }}
              disabled={!isValidInput()}
            >
              <Play className="h-4 w-4" aria-hidden="true" />
              Run Simulation
            </button>
          )}
          {running && (
            <button className="btn-ghost !py-2" onClick={cancel} aria-busy="true">
              <X className="h-4 w-4" aria-hidden="true" />
              Cancel Run
            </button>
          )}
          {(result !== null || running) && (
            <button className="btn-ghost !py-2" onClick={reset}>
              <RotateCcw className="h-4 w-4" aria-hidden="true" />
              Reset
            </button>
          )}
        </div>

        {/* staged processing pipeline */}
        {running && (
          <ol
            className="mt-5 grid gap-x-8 gap-y-2.5 border-t border-border pt-4 sm:grid-cols-2 xl:grid-cols-3"
            aria-label="Simulation progress"
            aria-live="polite"
          >
            {[...STAGES, "Complete"].map((label, i) => {
              const done = stage !== null && i < stage;
              const active = stage === i;
              const isFinal = i === STAGES.length;
              return (
                <li key={label} className={cn("flex items-center gap-2.5 text-[0.8125rem]", !done && !active && "text-faint")} style={{ animationDelay: `${i * 80}ms` }}>
                  {done ? (
                    <CheckCircle2
                      className={cn("h-4 w-4 shrink-0", isFinal ? "text-success" : "text-foreground")}
                      aria-hidden="true"
                    />
                  ) : active ? (
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin text-foreground" aria-hidden="true" />
                  ) : (
                    <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                      <span className="h-1.5 w-1.5 rounded-full bg-white/[0.1]" aria-hidden="true" />
                    </span>
                  )}
                  <span className={cn(done || active ? "text-foreground" : "")}>{label}</span>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      {result && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 animate-in fade-in slide-in-from-bottom-2 duration-500 ease-out">
            {[
              { label: "Failed Payments", value: result.failedPayments, icon: AlertTriangle, tone: "text-muted-foreground" },
              { label: "Revenue at Risk", value: result.revenueAtRisk, icon: Wallet, tone: "text-error" },
              { label: "AI Recovered", value: result.aiRecovered, icon: CheckCircle2, tone: "text-success" },
              { label: "Incremental Revenue", value: result.incrementalRevenue, icon: TrendingUp, tone: "text-success" },
            ].map((c) => (
              <div key={c.label} className="rounded-xl bg-white/[0.03] p-4 transition-all duration-300 hover:bg-white/[0.05] hover:shadow-[0_8px_30px_-10px_rgb(124_127_245/0.15)] hover:-translate-y-1 hover:border-border/50 border border-transparent">
                <div className="flex items-center justify-between">
                  <p className="label-sm text-faint">{c.label}</p>
                  <c.icon className={`h-4 w-4 ${c.tone}`} aria-hidden="true" />
                </div>
                <p className={`num mt-2 font-display text-[1.75rem] font-bold ${c.tone}`}>
                  <CountUp value={c.value} format={c.label.includes("Revenue") ? formatLakh : (n) => n.toLocaleString("en-IN")} />
                </p>
              </div>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl bg-white/[0.03] p-5 animate-in fade-in slide-in-from-bottom-2 duration-500 ease-out" style={{ animationDelay: "100ms" }}>
              <p className="label-sm text-faint">Static vs AI Recovered</p>
              <CompareBars className="mt-5" staticValue={result.staticRecovered} aiValue={result.aiRecovered} />
              <p className="mt-5 text-[0.8125rem] text-muted-foreground">
                {formatPct(result.staticRate, 1)} → <span className="text-success">{formatPct(result.aiRate, 1)}</span> recovery rate
              </p>
            </div>
            <div className="rounded-xl bg-white/[0.03] p-5 animate-in fade-in slide-in-from-bottom-2 duration-500 ease-out" style={{ animationDelay: "150ms" }}>
              <p className="label-sm text-faint">Action Breakdown</p>
              <div className="mt-5 space-y-2.5 text-[0.8125rem]">
                {result.actionBreakdown.map((a, i) => (
                  <div key={a.action} className="flex items-center justify-between border-b border-border pb-2.5 last:border-0 animate-in fade-in slide-in-from-left-2 duration-300 ease-out" style={{ animationDelay: `${i * 50}ms` }}>
                    <span className="text-muted-foreground">{a.action}</span>
                    <span className="num text-foreground">
                      <CountUp value={a.count} format={(n) => n.toLocaleString("en-IN")} className="text-[0.8125rem]" />
                      <span className="ml-4 text-faint">{formatINR(a.recovered)}</span>
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-[0.6875rem] text-faint">
                {result.id} · {result.policyViolations} policy violations
              </p>
            </div>
          </div>
        </>
      )}

      {error && !running && (
        <div className="rounded-lg border border-error/20 bg-error/10 px-5 py-4 text-center animate-in fade-in slide-in-from-top-2 duration-200 ease-out">
          <div className="flex items-center justify-center gap-2 text-[0.8125rem] text-error">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            {error}
          </div>
          <button className="btn-primary mt-3 !py-1.5 text-[0.75rem]" onClick={start}>
            <RotateCcw className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
            Retry Simulation
          </button>
        </div>
      )}

      {!result && !running && !error && (
        <EmptyState
          icon={Play}
          title="No simulation results yet"
          copy="Set your batch parameters above and hit Run — results appear here in a few seconds."
        />
      )}
    </div>
  );
}
