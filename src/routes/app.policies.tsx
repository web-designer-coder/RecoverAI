import { useEffect, useState, useMemo } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { getPolicies, updatePolicies } from "@/lib/api";
import type { FailureCategory, PolicyRules, RecommendedAction } from "@/lib/types";
import { ACTION_LABELS, FAILURE_LABELS, formatINR } from "@/lib/format";
import { PageLoading, ErrorState } from "@/components/states";
import { Toggle } from "@/components/primitives";
import { toast } from "sonner";
import {
  Clock,
  AlertTriangle,
  RefreshCw,
  Shield,
  Target,
  CreditCard,
  UserX,
  Wifi,
  Ban,
  HelpCircle,
  Settings,
  CheckCircle2,
} from "lucide-react";

export const Route = createFileRoute("/app/policies")({
  head: () => ({
    meta: [
      { title: "Recovery Policies — RecoverAI" },
      { name: "description", content: "Bound AI recovery actions with retry limits, windows and confidence thresholds." },
      { property: "og:title", content: "Recovery Policies — RecoverAI" },
      { property: "og:description", content: "The guardrails every AI recommendation must pass." },
    ],
  }),
  component: PoliciesPage,
});

const ACTIONS: RecommendedAction[] = ["RETRY", "PAYMENT_UPDATE", "NOTIFY", "STOP", "ESCALATE"];

function PoliciesPage() {
  const [policies, setPolicies] = useState<PolicyRules | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Interactive evaluator state (must be before any early returns — React Hooks rules)
  const [evalCategory, setEvalCategory] = useState<FailureCategory>("INSUFFICIENT_FUNDS");
  const [evalAmount, setEvalAmount] = useState(5000);
  const [evalRetries, setEvalRetries] = useState(0);
  const [evalConfidence, setEvalConfidence] = useState(85);

  useEffect(() => {
    let alive = true;
    getPolicies()
      .then((p) => {
        if (alive) setPolicies(p);
      })
      .catch((err) => {
        console.error('Failed to load policies:', err);
        if (alive) {
          setError(err instanceof Error ? err.message : 'Failed to load policies');
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  // All hooks before any conditional return — Rules of Hooks
  const strategyCards = useMemo(() => [
    {
      category: "INSUFFICIENT_FUNDS" as FailureCategory,
      icon: <Clock className="h-5 w-5 text-muted-foreground" />,
      title: "Insufficient Funds",
      description: "Optimal window retry with progressive delay",
      rationale: "These failures are typically transient — the customer's account may be temporarily low. Retrying at the optimal window (typically 12-48 hours) maximizes recovery probability.",
      strategy: "Delay → Retry",
      color: "border-ai/20 bg-ai/[0.04]",
    },
    {
      category: "EXPIRED_CARD" as FailureCategory,
      icon: <CreditCard className="h-5 w-5 text-warning" />,
      title: "Expired Card",
      description: "Customer notification for payment method update",
      rationale: "Cards expire monthly — the customer must update their payment details. Proactive notification with a secure update link recovers more than silent retries.",
      strategy: "Notify → Update",
      color: "border-warning/20 bg-warning/[0.04]",
    },
    {
      category: "NETWORK_FAILURE" as FailureCategory,
      icon: <Wifi className="h-5 w-5 text-success" />,
      title: "Network Failure",
      description: "Immediate retry with exponential backoff",
      rationale: "Network failures are usually momentary — immediate retry often succeeds. If not, exponential backoff prevents gateway flooding while capturing recovery opportunities.",
      strategy: "Immediate Retry",
      color: "border-success/20 bg-success/[0.04]",
    },
    {
      category: "BANK_DECLINE" as FailureCategory,
      icon: <Ban className="h-5 w-5 text-error" />,
      title: "Bank Decline",
      description: "Escalation for manual review",
      rationale: "Permanent bank declines require human judgment — potential fraud, account restrictions, or compliance issues. Automatic retries waste resources and may violate regulations.",
      strategy: "Escalate → Review",
      color: "border-error/20 bg-error/[0.04]",
    },
    {
      category: "INVALID_DETAILS" as FailureCategory,
      icon: <AlertTriangle className="h-5 w-5 text-warning" />,
      title: "Invalid Details",
      description: "Customer outreach for correction",
      rationale: "Incorrect payment details (wrong CVV, address mismatch) require customer action. Clear notification with specific guidance recovers more than generic retry attempts.",
      strategy: "Notify → Correct",
      color: "border-warning/20 bg-warning/[0.04]",
    },
    {
      category: "OTHER" as FailureCategory,
      icon: <HelpCircle className="h-5 w-5 text-muted-foreground" />,
      title: "Other Failures",
      description: "Conservative escalation for unknown errors",
      rationale: "Unrecognized failure patterns need human analysis to prevent incorrect automated actions. Conservative escalation protects against unintended consequences.",
      strategy: "Escalate → Analyze",
      color: "border-border bg-white/[0.02]",
    },
  ], []);

  const validate = () => {
    if (!policies) return false;
    if (policies.maxRetries < 0 || policies.maxRetries > 10) return false;
    if (policies.recoveryWindowDays < 1 || policies.recoveryWindowDays > 30) return false;
    if (policies.minConfidence < 0 || policies.minConfidence > 100) return false;
    if (policies.highValueThreshold < 0) return false;
    return true;
  };

  const handleSave = async () => {
    if (!policies || !validate()) {
      toast.error("Invalid values", { description: "Please check all fields are within valid ranges" });
      return;
    }
    setSaving(true);
    try {
      await updatePolicies(policies);
      setSaved(true);
      toast.success("Policies saved", { description: "Changes apply to all pending recoveries" });
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to save policies";
      toast.error("Save failed", { description: msg });
    } finally {
      setSaving(false);
    }
  };

  const evaluatePayment = useMemo(() => {
    if (!policies || !policies.failureRules) return [];
    const checks: { label: string; detail: string; passed: boolean; kind: "pass" | "fail" | "escalate" }[] = [];

    // 1. Action allowed for category
    const allowedAction = policies.failureRules[evalCategory];
    checks.push({
      label: "Category Action",
      detail: `${FAILURE_LABELS[evalCategory]} → ${ACTION_LABELS[allowedAction]}`,
      passed: true,
      kind: "pass",
    });

    // 2. Retry count check
    const retryOk = evalRetries < policies.maxRetries;
    checks.push({
      label: "Retry Limit",
      detail: `${evalRetries} of ${policies.maxRetries} max retries used`,
      passed: retryOk,
      kind: retryOk ? "pass" : "fail",
    });

    // 3. Confidence threshold
    const confOk = evalConfidence >= policies.minConfidence;
    checks.push({
      label: "AI Confidence",
      detail: `${evalConfidence}% confidence vs ${policies.minConfidence}% minimum`,
      passed: confOk,
      kind: confOk ? "pass" : "fail",
    });

    // 4. High-value escalation
    if (evalAmount >= policies.highValueThreshold && policies.escalateHighValue) {
      checks.push({
        label: "High-Value Escalation",
        detail: `₹${evalAmount.toLocaleString("en-IN")} ≥ ₹${policies.highValueThreshold.toLocaleString("en-IN")} threshold`,
        passed: false,
        kind: "escalate",
      });
    } else {
      checks.push({
        label: "High-Value Check",
        detail: policies.escalateHighValue
          ? `₹${evalAmount.toLocaleString("en-IN")} < ₹${policies.highValueThreshold.toLocaleString("en-IN")} threshold`
          : "High-value escalation disabled",
        passed: true,
        kind: "pass",
      });
    }

    // 5. Duplicate prevention
    if (policies.preventDuplicates && evalRetries > 0) {
      checks.push({
        label: "Duplicate Prevention",
        detail: "Recovery already attempted — new attempt flagged",
        passed: false,
        kind: "fail",
      });
    } else {
      checks.push({
        label: "Duplicate Prevention",
        detail: policies.preventDuplicates ? "No prior attempts detected" : "Disabled",
        passed: true,
        kind: "pass",
      });
    }

    return checks;
  }, [policies, evalCategory, evalAmount, evalRetries, evalConfidence]);

  const evalVerdict = useMemo(() => {
    if (evaluatePayment.length === 0) return { decision: "PENDING", color: "text-muted-foreground" };
    const hasEscalate = evaluatePayment.some((c) => c.kind === "escalate");
    const hasFail = evaluatePayment.some((c) => c.kind === "fail" && c.label !== "Duplicate Prevention");
    if (hasEscalate) return { decision: "ESCALATED", color: "text-warning" };
    if (hasFail) return { decision: "BLOCKED", color: "text-error" };
    return { decision: "APPROVED", color: "text-success" };
  }, [evaluatePayment]);

  if (error) return <ErrorState title="Couldn't load policies" copy={error} />;
  if (!policies) return <PageLoading label="Loading policies…" />;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="headline-md text-foreground">Policies</h1>
          <p className="mt-2 max-w-xl text-[0.8125rem] text-muted-foreground">
            Every AI recommendation must pass these bounds before execution. Saved changes apply
            to policy checks across the queue and payment details immediately.
          </p>
        </div>
        <button
          className="btn-primary !py-2"
          onClick={handleSave}
          disabled={saving || !validate()}
          aria-busy={saving}
        >
          {saving ? (
            <>
              <svg className="h-4 w-4 animate-spin mr-2" viewBox="0 0 24 24" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Saving…
            </>
          ) : saved ? (
            <>
              <svg className="h-4 w-4 mr-2" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              Saved
            </>
          ) : (
            "Save Policies"
          )}
        </button>
      </header>

      {/* Recovery Strategy Overview */}
      <section className="rounded-xl bg-white/[0.03] p-6" aria-label="Recovery strategies">
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-foreground" aria-hidden="true" />
          <p className="label-sm text-faint">Recovery Strategies by Failure Type</p>
        </div>
        <p className="mt-1.5 text-[0.75rem] text-faint">
          Each failure category has a tailored recovery strategy optimized for its specific characteristics and customer behavior patterns.
        </p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {strategyCards.map((card) => (
            <div
              key={card.category}
              className={`rounded-lg border p-4 transition-all duration-200 hover:border-border/50 hover:shadow-[0_4px_20px_-8px_rgba(0,0,0,0.2)] ${card.color}`}
            >
              <div className="flex items-start gap-3">
                <div className="p-2 rounded-lg bg-background/50">{card.icon}</div>
                <div className="min-w-0">
                  <p className="text-[0.8125rem] font-medium text-foreground">{card.title}</p>
                  <p className="text-[0.75rem] text-muted-foreground mt-0.5">{card.description}</p>
                </div>
              </div>
              <p className="mt-3 text-[0.75rem] leading-relaxed text-muted-foreground">{card.rationale}</p>
              <div className="mt-3 flex items-center gap-2">
                <span className="text-[0.6875rem] font-medium text-faint uppercase tracking-wider">Strategy:</span>
                <span className="px-2 py-0.5 rounded text-[0.6875rem] font-medium bg-white/[0.06] text-foreground">{card.strategy}</span>
              </div>
              <div className="mt-2">
                <span className="text-[0.6875rem] font-medium text-faint">Current Action: </span>
                <span className="text-[0.6875rem] font-semibold text-foreground">{ACTION_LABELS[policies.failureRules[card.category]]}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="rounded-xl bg-white/[0.03] p-6 transition-all duration-200 hover:border-border/50 hover:shadow-[0_4px_20px_-8px_rgba(0,0,0,0.2)] border border-transparent">
        <p className="label-sm text-faint">Limits</p>
        <p className="mt-1.5 text-[0.75rem] text-faint">
          Hard ceilings enforced on every recovery — a payment exceeding any limit is blocked or escalated.
        </p>
        <div className="mt-5 grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {(
            [
              { key: "maxRetries", label: "Max Retries", min: 0, max: 10 },
              { key: "recoveryWindowDays", label: "Recovery Window (days)", min: 1, max: 30 },
              { key: "minConfidence", label: "Min Confidence (%)", min: 0, max: 100 },
              { key: "highValueThreshold", label: "High Value Threshold (₹)", min: 0, max: 1000000 },
            ] as { key: "maxRetries" | "recoveryWindowDays" | "minConfidence" | "highValueThreshold"; label: string; min: number; max: number }[]
          ).map((n) => (
            <label key={n.key} className="block">
              <span className="label-sm text-faint">{n.label}</span>
              <input
                type="number"
                value={policies[n.key]}
                onChange={(e) => setPolicies({ ...policies, [n.key]: Number(e.target.value) })}
                min={n.min}
                max={n.max}
                className="input-field num mt-2 w-full transition-all duration-200 hover:border-border/50 focus:ring-2 focus:ring-foreground/30 focus:border-foreground"
              />
            </label>
          ))}
        </div>
      </div>

      <div className="rounded-xl bg-white/[0.03] p-6 transition-all duration-200 hover:border-border/50 hover:shadow-[0_4px_20px_-8px_rgba(0,0,0,0.2)] border border-transparent">
        <p className="label-sm text-faint">Failure Type → Action</p>
        <p className="mt-1.5 text-[0.75rem] text-faint">
          The bounded action the AI may take for each failure category — STOP permanently halts recovery.
        </p>
        <div className="mt-5 space-y-3">
          {(Object.keys(policies.failureRules) as FailureCategory[]).map((cat) => (
            <div key={cat} className="flex items-center justify-between gap-4 border-b border-border pb-3 last:border-0 transition-colors duration-150 hover:bg-white/[0.02] rounded px-2 -mx-2">
              <span className="text-[0.8125rem] text-muted-foreground">{FAILURE_LABELS[cat]}</span>
              <select
                value={policies.failureRules[cat]}
                onChange={(e) =>
                  setPolicies({
                    ...policies,
                    failureRules: {
                      ...policies.failureRules,
                      [cat]: e.target.value as RecommendedAction,
                    },
                  })
                }
                className="input-field transition-all duration-200 hover:border-border/50 focus:ring-2 focus:ring-foreground/30 focus:border-foreground"
              >
                {ACTIONS.map((a) => (
                  <option key={a} value={a}>
                    {ACTION_LABELS[a]}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl bg-white/[0.03] p-6 transition-all duration-200 hover:border-border/50 hover:shadow-[0_4px_20px_-8px_rgba(0,0,0,0.2)] border border-transparent">
        <p className="label-sm text-faint">Controls</p>
        <p className="mt-1.5 text-[0.75rem] text-faint">
          Governance switches — duplicate protection and the audit log should stay on in production.
        </p>
        <div className="mt-5 space-y-3">
          {(
            [
              { key: "preventDuplicates", label: "Prevent duplicate attempts" },
              { key: "requirePolicyApproval", label: "Require policy approval before execution" },
              { key: "maintainAuditLog", label: "Maintain immutable audit log" },
              { key: "escalateHighValue", label: "Escalate high-value failures" },
            ] as { key: "preventDuplicates" | "requirePolicyApproval" | "maintainAuditLog" | "escalateHighValue"; label: string }[]
          ).map((t) => (
            <div key={t.key} className="flex items-center justify-between gap-4 border-b border-border pb-3 text-[0.8125rem] last:border-0 transition-colors duration-150 hover:bg-white/[0.02] rounded px-2 -mx-2">
              <span className="text-muted-foreground">{t.label}</span>
              <Toggle
                checked={policies[t.key]}
                onChange={(checked) => setPolicies({ ...policies, [t.key]: checked })}
                label={t.label}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Interactive Policy Evaluator */}
      <section className="rounded-xl bg-white/[0.03] p-6 transition-all duration-200 hover:border-border/50 hover:shadow-[0_4px_20px_-8px_rgba(0,0,0,0.2)] border border-transparent" aria-label="Policy evaluator">
        <div className="flex items-center gap-2">
          <Settings className="h-4 w-4 text-foreground" aria-hidden="true" />
          <p className="label-sm text-faint">Policy Evaluator Preview</p>
        </div>
        <p className="mt-1.5 text-[0.75rem] text-faint">
          Test how a hypothetical payment would be evaluated under your current policy rules.
        </p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="block">
            <span className="label-sm text-faint">Failure Category</span>
            <select
              value={evalCategory}
              onChange={(e) => setEvalCategory(e.target.value as FailureCategory)}
              className="input-field mt-2 w-full transition-all duration-200 hover:border-border/50 focus:ring-2 focus:ring-foreground/30 focus:border-foreground"
            >
              {Object.keys(policies.failureRules).map((cat) => (
                <option key={cat} value={cat}>{FAILURE_LABELS[cat as FailureCategory]}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="label-sm text-faint">Amount (₹)</span>
            <input
              type="number"
              value={evalAmount}
              onChange={(e) => setEvalAmount(Number(e.target.value))}
              min={0}
              className="input-field num mt-2 w-full transition-all duration-200 hover:border-border/50 focus:ring-2 focus:ring-foreground/30 focus:border-foreground"
            />
          </label>
          <label className="block">
            <span className="label-sm text-faint">Prior Retries</span>
            <input
              type="number"
              value={evalRetries}
              onChange={(e) => setEvalRetries(Number(e.target.value))}
              min={0}
              max={policies.maxRetries + 2}
              className="input-field num mt-2 w-full transition-all duration-200 hover:border-border/50 focus:ring-2 focus:ring-foreground/30 focus:border-foreground"
            />
          </label>
          <label className="block">
            <span className="label-sm text-faint">AI Confidence (%)</span>
            <input
              type="number"
              value={evalConfidence}
              onChange={(e) => setEvalConfidence(Number(e.target.value))}
              min={0}
              max={100}
              className="input-field num mt-2 w-full transition-all duration-200 hover:border-border/50 focus:ring-2 focus:ring-foreground/30 focus:border-foreground"
            />
          </label>
        </div>

        {/* Evaluator Results */}
        {evaluatePayment.length > 0 && (
          <div className="mt-5 space-y-3">
            <div className="flex items-center gap-3">
              <span className="text-[0.75rem] text-faint">Verdict:</span>
              <span className={`text-[0.8125rem] font-semibold ${evalVerdict.color}`}>
                {evalVerdict.decision}
              </span>
            </div>
            <div className="space-y-2">
              {evaluatePayment.map((check) => (
                <div key={check.label} className="flex items-center gap-3 text-[0.75rem]">
                  <span className="flex-shrink-0" aria-hidden="true">
                    {check.kind === "pass" ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                    ) : check.kind === "escalate" ? (
                      <AlertTriangle className="h-3.5 w-3.5 text-warning" />
                    ) : (
                      <Ban className="h-3.5 w-3.5 text-error" />
                    )}
                  </span>
                  <span className="font-medium text-muted-foreground min-w-[120px]">{check.label}</span>
                  <span className="text-faint">{check.detail}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
