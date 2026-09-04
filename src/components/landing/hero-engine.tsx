import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  BrainCircuit,
  Check,
  Crosshair,
  Gauge,
  Pause,
  Play,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Live recovery-engine visualization.
 * A payment signal travels DETECT → DIAGNOSE → PREDICT → DECIDE → POLICY → RECOVER.
 */

interface Stage {
  id: string;
  label: string;
  icon: typeof Crosshair;
  render: (active: boolean, done: boolean) => { title: string; meta?: string };
}

const STAGES: Stage[] = [
  {
    id: "failed",
    label: "Payment Failed",
    icon: XCircle,
    render: () => ({ title: "PAY_82931", meta: "₹8,499" }),
  },
  {
    id: "detect",
    label: "Detect",
    icon: Crosshair,
    render: () => ({ title: "Revenue at risk", meta: "₹8,499 flagged" }),
  },
  {
    id: "diagnose",
    label: "Diagnose",
    icon: BrainCircuit,
    render: () => ({ title: "Insufficient Funds", meta: "91% confidence" }),
  },
  {
    id: "predict",
    label: "Predict",
    icon: Gauge,
    render: () => ({ title: "Recovery probability", meta: "74%" }),
  },
  {
    id: "decide",
    label: "Decide",
    icon: Sparkles,
    render: () => ({ title: "Retry · Aug 28", meta: "09:00 optimal" }),
  },
  {
    id: "policy",
    label: "Policy",
    icon: ShieldCheck,
    render: () => ({ title: "Policy engine", meta: "Approved" }),
  },
  {
    id: "recover",
    label: "Recover",
    icon: Check,
    render: () => ({ title: "₹8,499", meta: "Recovered" }),
  },
];

const STAGE_MS = [1100, 900, 1000, 1200, 900, 900, 2400]; // recover holds longer

export function HeroEngine() {
  const [stage, setStage] = useState(0);
  const [cycle, setCycle] = useState(0);
  const [prob, setProb] = useState(0);
  const [paused, setPaused] = useState(false);
  const [inViewport, setInViewport] = useState(true);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  // pause when scrolled out of viewport
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const first = entries[0];
        if (first) setInViewport(first.isIntersecting);
      },
      { threshold: 0.1 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const running = inViewport && !paused;

  // stage sequencer
  useEffect(() => {
    if (!running) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setStage(STAGES.length - 1);
      setProb(74);
      return;
    }
    let i = stage;
    const advance = () => {
      timers.current.push(
        setTimeout(() => {
          i += 1;
          if (i >= STAGES.length) {
            setStage(0);
            setProb(0);
            setCycle((c) => c + 1);
            return;
          }
          setStage(i);
          advance();
        }, STAGE_MS[i] ?? 900),
      );
    };
    advance();
    const copy = timers.current;
    return () => copy.forEach(clearTimeout);
  }, [cycle, running]);

  // probability count-up while PREDICT is active
  useEffect(() => {
    if (stage < 3 || !running) return;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 700);
      setProb(Math.round(74 * (1 - Math.pow(1 - t, 3))));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [stage, cycle, running]);

  const progress = useMemo(() => stage / (STAGES.length - 1), [stage]);
  const recovered = stage === STAGES.length - 1;

  return (
    <div
      ref={wrapRef}
      className="feature-dark noise relative overflow-hidden rounded-2xl border border-border shadow-[0_24px_60px_-32px_rgb(18_20_22/0.55)]"
      role="img"
      aria-label="Live recovery engine: failed payment PAY_82931 moving through detect, diagnose, predict, decide, policy and recover stages, ending with ₹8,499 recovered"
    >
      {/* header strip */}
      <div className="relative z-10 flex items-center justify-between border-b border-border px-4 py-3 sm:px-5">
        <span className="label-sm inline-flex items-center gap-2 text-muted-foreground">
          <span className="inline-flex gap-1" aria-hidden="true">
            <span className="h-1.5 w-1.5 rounded-full bg-error/70" />
            <span className="h-1.5 w-1.5 rounded-full bg-warning/70" />
            <span className="h-1.5 w-1.5 rounded-full bg-success/70" />
          </span>
          Recovery Engine · Live
        </span>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "chip",
              recovered ? "chip-success" : paused ? "chip-neutral" : "chip-ai",
              "transition-colors duration-500",
            )}
          >
            <span className={cn("h-1.5 w-1.5 rounded-full", recovered ? "bg-success" : paused ? "bg-muted-foreground" : "bg-ai pulse-dot")} />
            {recovered ? "Recovered" : paused ? "Paused" : stage === 0 ? "Signal lost" : "Processing"}
          </span>
          <button
            onClick={() => setPaused((p) => !p)}
            className="grid h-7 w-7 place-items-center rounded-md text-muted-foreground transition-all duration-200 hover:bg-surface-high hover:text-foreground hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ai-vivid active:scale-95"
            aria-label={paused ? "Resume animation" : "Pause animation"}
          >
            {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      <div className="relative z-10 px-4 py-6 sm:px-6 sm:py-8">
        {/* connecting rail — desktop horizontal */}
        <div className="absolute left-[7%] right-[7%] top-[4.65rem] hidden h-px bg-border-strong lg:block" aria-hidden="true">
          <div
            className="h-full origin-left"
            style={{
              transform: `scaleX(${progress})`,
              background: recovered
                ? "linear-gradient(90deg, var(--ai), var(--ai-vivid) 60%, var(--success-vivid))"
                : "linear-gradient(90deg, #6b7080, #9498a6)",
              boxShadow: "0 0 8px color-mix(in srgb, var(--ai) 35%, transparent)",
              transition: "transform 0.85s cubic-bezier(0.22,1,0.36,1)",
            }}
          />
          {/* travelling signal */}
          <div
            className="absolute top-1/2 h-2 w-2 -translate-y-1/2 rounded-full"
            style={{
              left: `${progress * 100}%`,
              background: recovered ? "var(--success-vivid)" : "var(--ai)",
              boxShadow: recovered
                ? "0 0 10px 2px color-mix(in srgb, var(--success-vivid) 45%, transparent)"
                : "0 0 10px 2px color-mix(in srgb, var(--ai) 45%, transparent)",
              transition: "left 0.85s cubic-bezier(0.22,1,0.36,1), background 0.4s, box-shadow 0.4s",
            }}
          />
        </div>

        {/* connecting rail — mobile vertical */}
        <div className="absolute bottom-32 left-[1.1rem] top-6 w-px bg-border-strong sm:left-[2.15rem] lg:hidden" aria-hidden="true">
          <div
            className="w-full origin-top"
            style={{
              transform: `scaleY(${progress})`,
              height: "100%",
              background: recovered
                ? "linear-gradient(180deg, var(--ai), var(--ai-vivid) 60%, var(--success-vivid))"
                : "linear-gradient(180deg, #6b7080, #9498a6)",
              boxShadow: "0 0 8px color-mix(in srgb, var(--ai) 35%, transparent)",
              transition: "transform 0.85s cubic-bezier(0.22,1,0.36,1)",
            }}
          />
        </div>

        <ol className="relative flex flex-col gap-3 lg:grid lg:grid-cols-7 lg:gap-2">
          {STAGES.map((s, i) => {
            const active = i === stage;
            const done = i < stage;
            const isRecover = s.id === "recover";
            const body = s.render(active, done);
            const Icon = s.icon;

            return (
              <li key={s.id} className="flex items-center gap-3 lg:flex-col lg:gap-0 lg:text-center">
                <div
                  className={cn(
                    "relative z-10 grid h-9 w-9 shrink-0 place-items-center rounded-lg border transition-all duration-500 sm:h-11 sm:w-11 sm:rounded-xl",
                    s.id === "failed" && "border-error/40 bg-surface text-error",
                    s.id !== "failed" && !isRecover && "border-border-strong bg-surface text-muted-foreground",
                    active && !isRecover && s.id !== "failed" && "border-ai/70 bg-surface-high text-ai pulse-node",
                    done && "border-ai/40 bg-surface-high text-ai",
                    isRecover && recovered && "border-success/60 bg-surface-high text-success glow-success",
                    isRecover && !recovered && "border-border-strong text-muted-foreground",
                  )}
                >
                  {done && !isRecover ? (
                    <Check className="h-4 w-4 sm:h-4.5 sm:w-4.5" strokeWidth={2.2} />
                  ) : (
                    <Icon className="h-4 w-4 sm:h-4.5 sm:w-4.5" strokeWidth={1.8} />
                  )}
                </div>

                {/* mobile: show label inline, details only for active stage */}
                <div className="min-w-0 lg:mt-3">
                  <p
                    className={cn(
                      "label-sm transition-colors duration-500",
                      active ? "text-foreground" : done ? "text-muted-foreground" : "text-muted-foreground",
                    )}
                  >
                    {String(i).padStart(2, "0")} · {s.label}
                  </p>
                  {/* details: always on desktop, only active on mobile */}
                  <div className={cn("lg:block", !active && !done && "hidden")}>
                    <p
                      className={cn(
                        "mt-1 text-sm font-medium transition-colors duration-500",
                        "text-foreground",
                        isRecover && recovered && "text-success",
                      )}
                    >
                      {s.id === "predict" && stage >= 3 ? `${prob}% recovery probability` : body.title}
                    </p>
                    {body.meta && (
                      <p
                        className={cn(
                          "num mt-0.5 text-xs transition-colors duration-500",
                          isRecover && recovered
                            ? "text-success"
                            : active || done
                              ? "text-ai"
                              : "text-muted-foreground",
                        )}
                      >
                        {s.id === "predict" && stage >= 3 ? "predicted success" : body.meta}
                      </p>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>

        {/* footer strip */}
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 lg:mt-8">
          <div className="flex items-center gap-5">
            <div>
              <p className="label-sm text-muted-foreground">Expected recovery</p>
              <p className="num mt-0.5 text-sm text-foreground">₹6,282</p>
            </div>
            <div>
              <p className="label-sm text-muted-foreground">Policy</p>
              <p
                className={cn(
                  "num mt-0.5 text-sm transition-colors duration-500",
                  stage >= 5 ? "text-success" : "text-muted-foreground",
                )}
              >
                {stage >= 5 ? "APPROVED ✓" : "PENDING"}
              </p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            Bounded by merchant policies
            <ArrowRight className="h-3.5 w-3.5" />
          </span>
        </div>
      </div>
    </div>
  );
}
