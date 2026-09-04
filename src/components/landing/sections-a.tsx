import { Link, useNavigate } from "@tanstack/react-router";
import {
  ArrowDown,
  ArrowRight,
  BadgeCheck,
  Ban,
  Bell,
  Clock,
  CreditCard,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Timer,
  TrendingUp,
} from "lucide-react";
import { HeroEngine } from "./hero-engine";
import { SectionHeading, Reveal, CountUp } from "@/components/primitives";
import { CompareBars } from "@/components/charts";
import { useScrollProgress, useInView } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";

/* ================================================================== */
/* HERO — asymmetric split, left copy / right engine                   */
/* ================================================================== */

export function Hero() {
  const navigate = useNavigate();
  const session = useAuth();

  return (
    <section className="relative overflow-hidden bg-background">
      {/* horizon line */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-border-strong to-transparent"
      />

      <div className="container-grid relative pt-28 pb-16 sm:pt-36 md:pt-40 md:pb-20">
        <div className="grid items-center gap-14 lg:grid-cols-12 lg:gap-10">
          {/* left: copy + CTAs */}
          <Reveal className="lg:col-span-5">
            <h1 className="display-xl text-foreground">
              Revenue
              <br />
              shouldn’t
              <br />
              disappear.
            </h1>

            <p className="mt-7 max-w-md text-[1.0625rem] leading-[1.55] text-[#9ca3af]">
              RecoverAI analyses every failed payment, understands the
              customer and failure context, predicts the best recovery action
              — and executes it within your policies.
            </p>

            <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
              <button
                onClick={() =>
                  navigate({ to: session ? "/app/dashboard" : "/signup" })
                }
                className="btn-primary !rounded-full !h-11 !px-5"
              >
                Start recovering
                <ArrowRight className="h-4 w-4" strokeWidth={2} />
              </button>
              <a
                href="#how-it-works"
                className="btn-ghost !rounded-full !h-11 !px-5"
              >
                See how it works
                <ArrowRight
                  className="ml-1.5 h-3.5 w-3.5 opacity-60 transition-all duration-200 group-hover:translate-x-0.5"
                  strokeWidth={2}
                />
              </a>
            </div>

            {/* inline metric strip — typographic, no card frame */}
            <dl className="mt-14 grid grid-cols-3 gap-x-6 sm:max-w-md">
              {[
                { k: "Recovery uplift", v: "+38%" },
                { k: "Decision latency", v: "120ms" },
                { k: "Actions audited", v: "100%" },
              ].map((s) => (
                <div key={s.k}>
                  <dt className="label-sm text-[#6f7683]">{s.k}</dt>
                  <dd className="num mt-1.5 text-[1.5rem] font-semibold tracking-tight text-foreground">
                    {s.v}
                  </dd>
                </div>
              ))}
            </dl>
          </Reveal>

          {/* right: engine visualization */}
          <Reveal className="lg:col-span-7" delay={120}>
            <HeroEngine />
          </Reveal>
        </div>
      </div>
    </section>
  );
}

/* ================================================================== */
/* PROBLEM — big stat, compact supporting data                        */
/* ================================================================== */

export function Problem() {
  return (
    <section id="product" className="bg-background">
      <div className="container-grid grid items-start gap-16 py-24 md:py-32 lg:grid-cols-12">
        {/* left: stat hero */}
        <Reveal className="lg:col-span-6">
          <p className="num text-5xl font-bold tracking-tight sm:text-6xl md:text-7xl lg:text-8xl">
            <CountUp
              value={4270000}
              format={(n) => `₹${(n / 100000).toFixed(1)}L`}
              duration={1400}
            />
          </p>
          <p className="mt-3 font-display text-lg font-semibold text-foreground sm:text-xl">
            lost every month to failed payments
          </p>
          <p className="mt-4 max-w-md text-[1rem] leading-[1.6] text-[#9ca3af]">
            Traditional retries treat all failures the same. RecoverAI determines
            what each payment needs — the right action, at the right moment.
          </p>
        </Reveal>

        {/* right: supporting metrics — typographic list */}
        <Reveal className="lg:col-span-6" delay={120}>
          <div className="grid gap-6 sm:grid-cols-2">
            {/* Failed payments */}
            <div>
              <dt className="label-sm text-[#6f7683]">Failed payments</dt>
              <dd className="mt-2 flex items-baseline gap-2">
                <p className="num text-3xl font-bold tracking-tight sm:text-4xl">
                  <CountUp value={600} duration={1400} />
                </p>
                <p className="ml-1 text-sm text-muted-foreground">per month</p>
              </dd>
            </div>

            {/* Static recovery */}
            <div>
              <dt className="label-sm text-[#6f7683]">Static recovery rate</dt>
              <dd className="mt-2 flex items-baseline gap-2">
                <p className="num text-3xl font-bold tracking-tight sm:text-4xl text-muted-foreground">
                  53%
                </p>
                <p className="ml-1 text-sm text-muted-foreground">of failures</p>
              </dd>
            </div>

            {/* RecoverAI recovery */}
            <div>
              <dt className="label-sm text-[#6f7683]">RecoverAI recovery rate</dt>
              <dd className="mt-2 flex items-baseline gap-2">
                <p className="num text-3xl font-bold tracking-tight sm:text-4xl text-foreground">
                  68.5%
                </p>
                <p className="ml-1 text-sm text-muted-foreground">of failures</p>
              </dd>
            </div>

            {/* Incremental revenue */}
            <div>
              <dt className="label-sm text-[#6f7683]">Incremental revenue</dt>
              <dd className="mt-2 flex items-baseline gap-2">
                <p className="num text-3xl font-bold tracking-tight sm:text-4xl text-success">
                  +₹3.2L
                </p>
                <p className="ml-1 text-sm text-muted-foreground">per month</p>
              </dd>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ================================================================== */
/* WORKFLOW — 6-step connected pipeline, scroll-activated              */
/* ================================================================== */

const WORKFLOW_STEPS = [
  {
    id: "01",
    name: "Detect",
    desc: "Every failed charge is captured the moment it happens and flagged as revenue at risk.",
  },
  {
    id: "02",
    name: "Understand",
    desc: "The failure is classified — insufficient funds, expired card, network error — with a confidence score.",
  },
  {
    id: "03",
    name: "Decide",
    desc: "The engine selects the optimal action and timing — retry, card update, or notification.",
  },
  {
    id: "04",
    name: "Protect",
    desc: "Every recommendation is checked against your retry limits, time windows, and stopping rules.",
  },
  {
    id: "05",
    name: "Execute",
    desc: "The bounded action runs and the payment is recovered — or safely halted.",
  },
  {
    id: "06",
    name: "Measure",
    desc: "Incremental revenue is measured against a static-retry baseline. Every step is audited.",
  },
];

export function Workflow() {
  const { ref, progress } = useScrollProgress<HTMLDivElement>();
  const activeCount = Math.floor(progress * (WORKFLOW_STEPS.length + 1));

  return (
    <section id="how-it-works" className="bg-background">
      <div ref={ref} className="container-grid py-20 md:py-28">
        <SectionHeading
          title="From failure to recovery."
          copy="One connected system. Each stage hands off to the next — no manual queues, no blind retries."
          className="mb-10"
        />

        {/* connected timeline */}
        <div className="mx-auto mt-14 max-w-3xl">
          {WORKFLOW_STEPS.map((step, i) => {
            const active = i < activeCount;
            const isLast = i === WORKFLOW_STEPS.length - 1;
            return (
              <div key={step.id} className="relative flex gap-5 sm:gap-6">
                {/* left rail: number + connecting line */}
                <div className="flex flex-col items-center">
                  <span
                    className={cn(
                      "grid h-10 w-10 shrink-0 place-items-center rounded-full border text-sm font-bold transition-all duration-700",
                      active
                        ? "border-ai/50 bg-ai/15 text-ai"
                        : "border-border-strong bg-muted-foreground/20 text-muted-foreground",
                    )}
                  >
                    {step.id}
                  </span>
                  {!isLast && (
                    <div
                      className={cn(
                        "w-px flex-1 transition-colors duration-700",
                        i < activeCount - 1
                          ? "bg-ai/40"
                          : "bg-muted-foreground/20",
                      )}
                      aria-hidden="true"
                    />
                  )}
                </div>

                {/* right: content */}
                <div className={cn("pb-10", isLast && "pb-0")}>
                  <p
                    className={cn(
                      "font-display text-lg font-semibold tracking-tight transition-colors duration-700 sm:text-xl",
                      active ? "text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {step.name}
                  </p>
                  <p
                    className={cn(
                      "mt-1.5 text-sm leading-relaxed transition-colors duration-700 sm:max-w-lg",
                      active
                        ? "text-muted-foreground"
                        : "text-muted-foreground",
                    )}
                  >
                    {step.desc}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ================================================================== */
/* AI DECISION — animated state machine with reasoning panel           */
/* ================================================================== */

const DECISION_STATES = [
  "FAILED",
  "ANALYZING",
  "PREDICTED",
  "POLICY APPROVED",
  "RECOVERED",
] as const;

export function DecisionShowcase() {
  const { ref, inView } = useInView<HTMLDivElement>(0.35);
  const [stateIdx, setStateIdx] = useState(0);

  useEffect(() => {
    if (!inView) return;
    const reduce = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    if (reduce) {
      setStateIdx(DECISION_STATES.length - 1);
      return;
    }
    const id = setInterval(() => {
      setStateIdx((i) => (i + 1) % DECISION_STATES.length);
    }, 1600);
    return () => clearInterval(id);
  }, [inView]);

  const state = DECISION_STATES[stateIdx];
  const recovered = state === "RECOVERED";

  return (
    <section className="bg-background">
      <div
        ref={ref}
        className="container-grid grid items-start gap-16 py-24 md:py-32 lg:grid-cols-12"
      >
        {/* left: editorial lead */}
        <Reveal className="lg:col-span-5">
          <h2 className="headline-lg text-foreground">
            Every decision,
            <br />
            <span className="text-muted-foreground">explained.</span>
          </h2>
          <p className="mt-5 max-w-md text-[1rem] leading-[1.6] text-[#9ca3af]">
            RecoverAI doesn’t just act — it shows its reasoning. The
            customer, the failure, the prediction and the policy that
            authorised the action are all surfaced before a single rupee
            moves.
          </p>
        </Reveal>

        {/* right: intelligence composition — Why this decision? */}
        <Reveal className="lg:col-span-7" delay={120}>
          <div className="relative rounded-2xl border border-white/[0.06] bg-[#0c0d12]/80 p-6 sm:p-8 backdrop-blur-sm">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-4">
              <div className="flex items-center gap-2.5">
                <span className="grid h-6 w-6 place-items-center rounded-md bg-ai/10 text-ai">
                  <Sparkles className="h-3.5 w-3.5" strokeWidth={1.8} />
                </span>
                <p className="text-[0.8125rem] font-medium text-foreground">
                  Why this decision?
                </p>
              </div>
              <span
                className={cn(
                  "chip transition-all duration-500",
                  recovered
                    ? "chip-success"
                    : state === "FAILED"
                      ? "chip-error"
                      : "chip-ai",
                )}
              >
                {state}
              </span>
            </div>

            <dl className="mt-6 grid grid-cols-1 gap-y-5 sm:grid-cols-2 sm:gap-x-8 sm:gap-y-6">
              {[
                { k: "Customer", v: "Returning customer" },
                { k: "Failure", v: "Temporary — insufficient funds" },
                { k: "History", v: "8 successful prior payments" },
                { k: "Window", v: "27 – 29 of the month" },
                {
                  k: "Prediction",
                  v: stateIdx >= 2 ? "High recovery probability" : "Computing…",
                  accent: stateIdx >= 2 ? "text-ai" : "text-muted-foreground",
                },
                { k: "Retries used", v: "1 of 3" },
              ].map((row) => (
                <div key={row.k} className="min-w-0">
                  <dt className="label-sm text-[#6f7683]">{row.k}</dt>
                  <dd
                    className={cn(
                      "mt-1.5 text-[0.9375rem] font-medium text-foreground",
                      row.accent,
                    )}
                  >
                    {row.v}
                  </dd>
                </div>
              ))}
            </dl>

            <div className="mt-7 flex flex-wrap items-baseline justify-between gap-3 border-t border-white/[0.06] pt-5">
              <div>
                <p className="label-sm text-[#6f7683]">Recovery probability</p>
                <p
                  className={cn(
                    "num mt-1 text-[2rem] font-semibold tracking-tight transition-colors duration-500",
                    stateIdx >= 2 ? "text-ai" : "text-foreground",
                  )}
                >
                  {stateIdx >= 2 ? "74%" : "—"}
                </p>
              </div>
              <div className="text-right">
                <p className="label-sm text-[#6f7683]">Decision</p>
                <p className="mt-1 inline-flex items-center gap-1.5 text-[0.9375rem] font-medium text-foreground">
                  <RefreshCw className="h-3.5 w-3.5 text-ai" strokeWidth={1.8} />
                  Retry · Aug 28 · 09:00
                </p>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ================================================================== */
/* COMPARISON — AI vs static retries                                   */
/* ================================================================== */

export function Comparison() {
  return (
    <section className="bg-background">
      <div className="container-grid grid items-center gap-16 py-24 md:py-32 lg:grid-cols-12">
        {/* left: editorial */}
        <Reveal className="lg:col-span-5">
          <h2 className="headline-lg text-foreground">
            Recover more than traditional retries.
          </h2>
          <p className="mt-5 max-w-md text-[1rem] leading-[1.6] text-[#9ca3af]">
            Every recovery is measured against a static-retry baseline on the
            same payment population — so the lift is real, not modelled
            optimism.
          </p>

          {/* incremental revenue highlight */}
          <div className="mt-12 flex flex-col items-center gap-6 sm:flex-row sm:items-start">
            <span className="num font-display text-5xl font-bold tracking-tight text-success">
              +₹3.2L
            </span>
            <span className="text-[1.0625rem] font-medium text-muted-foreground">
              Incremental revenue per month
            </span>
          </div>
          <p className="mt-6 text-xs text-muted-foreground/80 max-w-md">
            Simulation values from the RecoverAI demo batch.
          </p>
        </Reveal>

        {/* right: chart + metrics */}
        <Reveal className="lg:col-span-7" delay={120}>
          <div className="relative rounded-2xl border border-white/[0.06] bg-[#0c0d12]/80 p-6 sm:p-8 backdrop-blur-sm">
            {/* chart */}
            <CompareBars staticValue={1110000} aiValue={1430000} className="mb-6" />
            {/* metrics grid */}
            <div className="grid gap-6 sm:grid-cols-2">
              {/* static recovery rate */}
              <div className="rounded-xl border border-white/[0.06] bg-[#0c0d12]/80 p-5 backdrop-blur-sm">
                <p className="label-sm text-[#6f7683]">Static recovery rate</p>
                <p className="mt-2 text-[1.875rem] font-semibold text-muted-foreground">
                  <CountUp
                    value={53}
                    decimals={1}
                    format={(n) => `${n.toFixed(1)}%`}
                  />
                </p>
                <p className="mt-2 text-xs text-muted-foreground/80">
                  of failures recovered by retries alone
                </p>
              </div>
              {/* AI recovery rate */}
              <div className="rounded-xl border border-white/[0.06] bg-[#0c0d12]/80 p-5 backdrop-blur-sm">
                <p className="label-sm text-[#6f7683]">RecoverAI recovery rate</p>
                <p className="mt-2 text-[1.875rem] font-semibold text-foreground">
                  <CountUp
                    value={68.5}
                    decimals={1}
                    format={(n) => `${n.toFixed(1)}%`}
                  />
                </p>
                <p className="mt-2 text-xs text-muted-foreground/80">
                  of failures recovered with AI
                </p>
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ================================================================== */
/* GUARDRAILS — AI with guardrails, decision flow + policy grid        */
/* ================================================================== */

const POLICY_EXAMPLES = [
  {
    icon: RefreshCw,
    name: "Maximum retries",
    desc: "Hard cap on attempts per payment.",
  },
  {
    icon: Clock,
    name: "Recovery window",
    desc: "Actions only inside your time bounds.",
  },
  {
    icon: TrendingUp,
    name: "Minimum confidence",
    desc: "Below threshold, AI hands off.",
  },
  {
    icon: Ban,
    name: "Hard decline handling",
    desc: "Non-retryable failures stop immediately.",
  },
  {
    icon: ShieldCheck,
    name: "Duplicate protection",
    desc: "No payment is ever charged twice.",
  },
];

export function Guardrails() {
  return (
    <section className="bg-background">
      <div className="container-grid py-24 md:py-32">
        <SectionHeading
          title="AI with guardrails."
          copy="AI recommends. Policies control. Every action is recorded."
          className="mb-12"
        />

        {/* two-column: decision flow + policy examples */}
        <div className="grid gap-12 lg:grid-cols-2 lg:items-start">
          {/* left: decision flow */}
          <Reveal>
            <div className="rounded-2xl border border-white/[0.06] bg-[#0c0d12]/80 p-6 backdrop-blur-sm">
              <p className="label-sm text-[#6f7683]">How an action is taken</p>

              {/* AI step */}
              <div className="mt-5 flex items-start gap-4">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-ai/30 bg-ai/10 text-ai">
                  <Sparkles className="h-5 w-5" strokeWidth={1.8} />
                </div>
                <div className="pt-1.5">
                  <p className="text-sm font-semibold text-foreground">AI Recommendation</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Retry · Aug 28 · 09:00 — 74% predicted success
                  </p>
                </div>
              </div>

              {/* arrow */}
              <div className="ml-5 flex items-center py-2" aria-hidden="true">
                <ArrowDown className="h-4 w-4 text-muted-foreground/60" />
              </div>

              {/* Policy step */}
              <div className="flex items-start gap-4">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-white/[0.06] bg-white/[0.03] text-muted-foreground">
                  <ShieldCheck className="h-5 w-5" strokeWidth={1.8} />
                </div>
                <div className="pt-1.5">
                  <p className="text-sm font-semibold text-foreground">Policy Engine</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Retry limits · windows · confidence · duplicates
                  </p>
                </div>
              </div>

              {/* arrow */}
              <div className="ml-5 flex items-center py-2" aria-hidden="true">
                <ArrowDown className="h-4 w-4 text-muted-foreground/60" />
              </div>

              {/* outcomes */}
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="flex items-center gap-3 rounded-xl border border-success/20 bg-success/5 px-4 py-3.5">
                  <BadgeCheck className="h-5 w-5 shrink-0 text-success" strokeWidth={1.8} />
                  <div>
                    <p className="text-sm font-semibold text-success">PASS → Execute</p>
                    <p className="text-xs text-muted-foreground">Bounded action proceeds</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 rounded-xl border border-error/20 bg-error/5 px-4 py-3.5">
                  <Ban className="h-5 w-5 shrink-0 text-error" strokeWidth={1.8} />
                  <div>
                    <p className="text-sm font-semibold text-error">BLOCK → Stop</p>
                    <p className="text-xs text-muted-foreground">Halted and logged for review</p>
                  </div>
                </div>
              </div>
            </div>
          </Reveal>

          {/* right: policy examples */}
          <Reveal delay={120}>
            <p className="label-sm mb-5 text-[#6f7683]">Policy controls available</p>
            <div className="grid gap-3 sm:grid-cols-2">
              {POLICY_EXAMPLES.map((p, i) => (
                <Reveal key={p.name} delay={i * 50}>
                  <div className="group flex items-start gap-3.5 rounded-xl border border-white/[0.06] bg-[#0c0d12]/60 p-4 transition-colors duration-300 hover:border-ai/20 hover:bg-[#0c0d12]/80">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-ai/20 bg-ai/10 text-ai">
                      <p.icon className="h-4 w-4" strokeWidth={1.6} />
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-foreground">{p.name}</p>
                      <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{p.desc}</p>
                    </div>
                  </div>
                </Reveal>
              ))}
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

/* ================================================================== */
/* PRODUCT PREVIEW — miniature command center                          */
/* ================================================================== */

const PREVIEW_METRICS = [
  { label: "Revenue at Risk", value: "₹18.42L", tone: "text-error" },
  { label: "Recovered Revenue", value: "₹11.73L", tone: "text-success" },
  { label: "Recovery Rate", value: "63.8%", tone: "text-foreground" },
  {
    label: "Incremental Revenue",
    value: "+₹2.14L",
    tone: "text-success",
  },
] as const;

const PREVIEW_CHART = [
  38, 44, 41, 52, 58, 54, 67, 72, 69, 81, 86, 92,
] as const;

const PREVIEW_QUEUE = [
  {
    id: "PAY_82931",
    customer: "CUS_2041",
    amount: "₹8,499",
    pct: "74%",
    status: "Scheduled",
  },
  {
    id: "PAY_77102",
    customer: "CUS_1187",
    amount: "₹12,300",
    pct: "61%",
    status: "Processing",
  },
  {
    id: "PAY_69514",
    customer: "CUS_3302",
    amount: "₹4,120",
    pct: "48%",
    status: "Queued",
  },
] as const;

const PREVIEW_NAV = [
  "Overview",
  "Queue",
  "Simulator",
  "Analytics",
  "Audit",
  "Policies",
] as const;

export function ProductPreview() {
  const navigate = useNavigate();
  const session = useAuth();

  return (
    <section className="bg-background">
      <div className="container-grid py-24 md:py-32">
        <SectionHeading
          title="One console for every recovery."
          copy="Revenue at risk, AI decisions, policy checks and outcomes — a single operating view for your payments team."
          className="mb-12"
        />

        <Reveal className="mt-14">
          <div className="relative mx-auto max-w-5xl overflow-hidden rounded-2xl border border-white/[0.06] bg-[#0c0d12]/80 shadow-[0_32px_64px_-24px_rgba(0,0,0,0.5)] backdrop-blur-sm">
            {/* window chrome */}
            <div
              className="flex items-center gap-2 border-b border-white/[0.06] px-4 py-2.5"
              aria-hidden="true"
            >
              <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
              <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
              <span className="h-2.5 w-2.5 rounded-full bg-white/10" />
              <span className="ml-3 text-xs text-[#6f7683]">
                RecoverAI · Overview
              </span>
            </div>

            <div className="flex">
              {/* mini sidebar */}
              <nav
                aria-hidden="true"
                className="hidden w-36 shrink-0 flex-col gap-0.5 border-r border-white/[0.06] p-3 sm:flex"
              >
                {PREVIEW_NAV.map((n, i) => (
                  <span
                    key={n}
                    className={cn(
                      "rounded-md px-2.5 py-1.5 text-[0.6875rem]",
                      i === 0
                        ? "bg-white/[0.04] font-medium text-foreground"
                        : "text-[#6f7683]",
                    )}
                  >
                    {i === 0 && (
                      <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-ai align-middle" />
                    )}
                    {n}
                  </span>
                ))}
                <span className="mt-auto px-2.5 pt-4 text-[0.6875rem] text-[#6f7683]">
                  Frontend demo · mock data
                </span>
              </nav>

              {/* mini workspace */}
              <div className="min-w-0 flex-1 p-4 sm:p-5">
                {/* top bar */}
                <div className="flex items-center gap-3">
                  <span className="flex h-7 min-w-0 flex-1 items-center rounded-md border border-white/[0.06] bg-white/[0.02] px-2.5 text-xs text-[#6f7683]">
                    Search payment or customer…
                  </span>
                  <span className="chip chip-success !px-2 !py-0.5 text-[0.6875rem]">
                    Operational
                  </span>
                  <Bell
                    className="h-3.5 w-3.5 shrink-0 text-[#6f7683]"
                    aria-hidden="true"
                  />
                  <span
                    className="grid h-6 w-6 place-items-center rounded-full bg-white/[0.06] text-[0.6875rem] font-semibold text-foreground"
                    aria-hidden="true"
                  >
                    A
                  </span>
                </div>

                {/* metric strip */}
                <div className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-white/[0.06] bg-white/[0.06] lg:grid-cols-4">
                  {PREVIEW_METRICS.map((m) => (
                    <div key={m.label} className="bg-[#0c0d12]/80 px-3 py-2.5">
                      <p className="label-sm truncate text-[0.6875rem] text-[#6f7683]">
                        {m.label}
                      </p>
                      <p
                        className={cn(
                          "num mt-1 text-sm font-bold tracking-tight",
                          m.tone,
                        )}
                      >
                        {m.value}
                      </p>
                    </div>
                  ))}
                </div>

                {/* chart + AI decision */}
                <div className="mt-3 grid gap-3 lg:grid-cols-5">
                  <div className="rounded-lg border border-white/[0.06] bg-[#0c0d12]/60 p-3.5 lg:col-span-3">
                    <p className="label-sm text-[0.6875rem] text-[#6f7683]">
                      Recovered vs Baseline
                    </p>
                    <div
                      className="mt-3 flex h-20 items-end gap-1.5"
                      aria-hidden="true"
                    >
                      {PREVIEW_CHART.map((v, i) => (
                        <span
                          key={i}
                          className={cn(
                            "flex-1 rounded-t-sm",
                            i === PREVIEW_CHART.length - 1
                              ? "bg-success/80"
                              : i % 2 === 0
                                ? "bg-ai/50"
                                : "bg-ai-vivid/70",
                          )}
                          style={{ height: `${v}%` }}
                        />
                      ))}
                    </div>
                  </div>
                  <div className="rounded-lg border border-ai/30 bg-ai/[0.04] p-3.5 lg:col-span-2">
                    <p className="label-sm inline-flex items-center gap-1.5 text-[0.6875rem] text-ai">
                      <Sparkles
                        className="h-3 w-3"
                        aria-hidden="true"
                      />
                      Next Best Action
                    </p>
                    <p className="num mt-2 text-xs font-medium text-foreground">
                      PAY_82931
                    </p>
                    <p className="mt-1 text-[0.6875rem] text-muted-foreground">
                      Retry at optimal window
                    </p>
                    <div className="mt-2.5 flex items-center justify-between text-[0.6875rem]">
                      <span className="num text-muted-foreground">
                        74% probability
                      </span>
                      <span className="chip chip-success !px-1.5 !py-0.5 text-[0.6875rem]">
                        Approved
                      </span>
                    </div>
                  </div>
                </div>

                {/* active recoveries */}
                <div className="mt-3 overflow-hidden rounded-lg border border-white/[0.06] bg-[#0c0d12]/60">
                  <p className="label-sm border-b border-white/[0.06] px-3.5 py-2 text-[0.6875rem] text-[#6f7683]">
                    Active Recoveries
                  </p>
                  {PREVIEW_QUEUE.map((r) => (
                    <div
                      key={r.id}
                      className="flex items-center gap-3 border-b border-white/[0.06] px-3.5 py-2 last:border-0"
                    >
                      <span className="num w-20 shrink-0 text-[0.6875rem] font-medium text-foreground">
                        {r.id}
                      </span>
                      <span className="num hidden w-16 text-[0.6875rem] text-[#6f7683] sm:inline">
                        {r.customer}
                      </span>
                      <span className="num ml-auto text-[0.6875rem] text-foreground">
                        {r.amount}
                      </span>
                      <span className="num w-9 text-right text-[0.6875rem] text-ai">
                        {r.pct}
                      </span>
                      <span className="chip chip-neutral !px-1.5 !py-0.5 text-[0.6875rem]">
                        {r.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </Reveal>

        <Reveal className="mt-10 text-center" delay={100}>
          <button
            onClick={() =>
              navigate({
                to: session ? "/app/dashboard" : "/signup",
              })
            }
            className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-white px-5 text-[0.875rem] font-medium text-[#0a0a0c] transition-all duration-200 hover:bg-white/90 active:scale-[0.98]"
          >
            Explore the Console
            <ArrowRight className="h-4 w-4" strokeWidth={2} />
          </button>
        </Reveal>
      </div>
    </section>
  );
}

/* ================================================================== */
/* SIMULATOR TEASER — metric flow + CTA                                */
/* ================================================================== */

export function SimulatorTeaser() {
  const navigate = useNavigate();
  const session = useAuth();

  const steps = [
    { value: 5000, label: "Transactions", format: (n: number) => n.toLocaleString("en-IN") },
    { value: 600, label: "Failed", format: (n: number) => n.toLocaleString("en-IN") },
    { value: 1430000, label: "AI Recovered", format: (n: number) => `₹${(n / 100000).toFixed(1)}L` },
    { value: 320000, label: "Incremental", format: (n: number) => `+₹${(n / 100000).toFixed(1)}L` },
  ];

  return (
    <section id="simulator" className="bg-background">
      <div className="container-grid py-24 md:py-32">
        <SectionHeading
          title="Prove the recovery."
          copy="Run your transaction history through the engine. See exactly what static retries recover — and what RecoverAI adds on top."
          className="mb-12"
        />

        <Reveal className="mt-14">
          <div className="mx-auto max-w-4xl rounded-2xl border border-white/[0.06] bg-[#0c0d12]/80 p-6 sm:p-8 backdrop-blur-sm shadow-[0_24px_48px_-24px_rgba(0,0,0,0.4)]">
            <div className="grid gap-8 sm:grid-cols-2 sm:gap-10 lg:grid-cols-4 lg:gap-6">
              {steps.map((s, i) => (
                <div key={s.label} className="relative">
                  {i > 0 && (
                    <div className="absolute -left-3 top-3 hidden h-0.5 w-6 bg-white/[0.08] lg:block" aria-hidden="true" />
                  )}
                  <p
                    className={cn(
                      "num font-display text-3xl font-bold tracking-tight",
                      i >= 2 ? "text-success" : i === 1 ? "text-error" : "text-foreground",
                    )}
                  >
                    <CountUp value={s.value} format={s.format} duration={1300} />
                  </p>
                  <p className="label-sm mt-2 text-[#6f7683]">{s.label}</p>
                </div>
              ))}
            </div>
            <div className="mt-8 flex flex-col items-start justify-between gap-4 border-t border-white/[0.06] pt-6 sm:flex-row sm:items-center">
              <p className="text-sm text-muted-foreground">
                Deterministic demo batch · 0 policy violations · full audit trail
              </p>
              <button
                className="inline-flex h-11 items-center justify-center gap-2 rounded-full bg-white px-5 text-[0.875rem] font-medium text-[#0a0a0c] transition-all duration-200 hover:bg-white/90 active:scale-[0.98]"
                onClick={() => navigate({ to: session ? "/app/simulator" : "/signup" })}
              >
                Run Simulation
                <ArrowRight className="h-4 w-4" strokeWidth={2} />
              </button>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* ================================================================== */
/* FINAL CTA — strong close                                           */
/* ================================================================== */

export function FinalCta() {
  const navigate = useNavigate();
  const session = useAuth();

  return (
    <section className="border-t border-border">
      <div className="container-grid py-24 text-center md:py-32">
        <Reveal>
          <h2 className="display-xl mx-auto max-w-3xl text-foreground">
            Don't just detect lost revenue.
            <br />
            Recover it.
          </h2>
          <p className="mt-6 mx-auto max-w-md text-[1.0625rem] leading-[1.55] text-[#9ca3af]">
            Start with the simulator or enter the dashboard. No credit card required.
          </p>
          <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <button
              className="btn-primary !rounded-full !h-11 !px-6"
              onClick={() =>
                navigate({
                  to: session ? "/app/dashboard" : "/signup",
                })
              }
            >
              Start recovering
              <ArrowRight className="h-4 w-4" strokeWidth={2} />
            </button>
            <Link
              to="/signup"
              className="btn-ghost !rounded-full !h-11 !px-6"
            >
              Create Account
            </Link>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/* re-exported icons used in preview file */
export { Bell, CreditCard, Timer };
