import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useCountUp, useInView } from "@/lib/hooks";
import { STATUS_LABELS } from "@/lib/format";

/* ---------------------------------------------------------------- */
/* Phase 35.5: Shared design-system primitives.                       */
/* All apps-pages should compose from these rather than introduce     */
/* new page-local styles.                                             */
/* ---------------------------------------------------------------- */

/* ---------------- status chip ---------------- */

const STATUS_TONES: Record<string, string> = {
  QUEUED: "chip-neutral",
  SCHEDULED: "chip-ai",
  PROCESSING: "chip-warning",
  RECOVERED: "chip-success",
  HALTED: "chip-error",
  NEEDS_ACTION: "chip-warning",
};

const STATUS_DOT: Record<string, string> = {
  QUEUED: "bg-muted-foreground",
  SCHEDULED: "bg-ai",
  PROCESSING: "bg-warning",
  RECOVERED: "bg-success",
  HALTED: "bg-error",
  NEEDS_ACTION: "bg-warning",
};

export function StatusChip({ status, className }: { status: string; className?: string }) {
  return (
    <span className={cn("chip", STATUS_TONES[status] ?? "chip-neutral", className)}>
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          STATUS_DOT[status] ?? "bg-muted-foreground",
          (status === "PROCESSING" || status === "SCHEDULED") && "pulse-dot",
        )}
      />
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

/* ---------------- animated number ---------------- */

export function CountUp({
  value,
  format,
  duration = 1100,
  decimals = 0,
  className,
}: {
  value: number;
  format?: (n: number) => string;
  duration?: number;
  decimals?: number;
  className?: string;
}) {
  const { ref, inView } = useInView<HTMLSpanElement>(0.4);
  const current = useCountUp(value, { active: inView, duration, decimals });
  const fmt = format ?? ((n: number) => n.toLocaleString("en-IN"));
  return (
    <span ref={ref} className={cn("num", className)}>
      {fmt(current)}
    </span>
  );
}

/* ---------------- spatial grouping primitives ---------------- */

/** WorkspaceGroup: spatial grouping with a label, optional description,
 *  and children. Use for information hierarchy instead of over-carding. */
export function WorkspaceGroup({
  label,
  title,
  description,
  actions,
  children,
  className,
  as: As = "section",
}: {
  label?: string;
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article";
}) {
  return (
    <As className={cn("page-section", className)}>
      {(label || title || description || actions) && (
        <header className="flex items-start justify-between gap-4 pb-4">
          <div className="min-w-0">
            {label && <p className="section-label mb-1.5">{label}</p>}
            {title && <h2 className="group-heading">{title}</h2>}
            {description && <p className="group-sub mt-1 max-w-xl">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn((label || title || description) && "pt-2")}>{children}</div>
    </As>
  );
}

/** MetaLine: a single horizontal piece of metadata with label + value. */
export function MetaLine({
  label,
  value,
  valueClass,
  className,
}: {
  label: string;
  value: ReactNode;
  valueClass?: string;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-start gap-1.5 py-1.5", className)}>
      <span className="text-[0.75rem] tracking-wide text-[#6b7080] uppercase font-mono">{label}</span>
      <span className={cn("num text-base font-semibold text-foreground block", valueClass)}>{value}</span>
    </div>
  );
}

/** MetricBlock: stat block with label + value + optional subline. */
export function MetricBlock({
  label,
  value,
  sub,
  tone,
  className,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "ai" | "success" | "error" | "warning";
  className?: string;
}) {
  const toneClass =
    tone === "ai" ? "text-[#8B8CF6]" :
    tone === "success" ? "text-[#34D399]" :
    tone === "error" ? "text-[#FF6B6B]" :
    tone === "warning" ? "text-[#F5C400]" :
    "text-foreground";
  return (
    <div className={cn("space-y-1.5", className)}>
      <p className="stat-label">{label}</p>
      <p className={cn("num text-2xl font-medium tracking-tight leading-none", toneClass)}>{value}</p>
      {sub && <p className="text-xs text-[#9498a6]">{sub}</p>}
    </div>
  );
}

/** Divider: subtle hairline between groups. */
export function Divider({ className }: { className?: string }) {
  return <div className={cn("section-divider", className)} aria-hidden="true" />;
}

/* ---------------- section heading (legacy landing) ---------------- */

export function SectionHeading({
  eyebrow,
  title,
  copy,
  tone = "dark",
  align = "center",
  className,
}: {
  eyebrow?: string;
  title: ReactNode;
  copy?: string;
  tone?: "dark" | "paper";
  align?: "center" | "left";
  className?: string;
}) {
  const dark = tone === "dark";
  return (
    <div
      className={cn(
        "reveal",
        align === "center" ? "mx-auto max-w-2xl text-center" : "max-w-2xl",
        className,
      )}
    >
      {eyebrow && (
        <p className={cn("label-sm", dark ? "text-ai" : "text-primary")}>{eyebrow}</p>
      )}
      <h2
        className={cn(
          "headline-lg mt-4",
          dark ? "text-foreground" : "text-paper-foreground",
        )}
      >
        {title}
      </h2>
      {copy && (
        <p
          className={cn(
            "mt-4 text-base leading-relaxed",
            dark ? "text-muted-foreground" : "text-paper-muted",
          )}
        >
          {copy}
        </p>
      )}
    </div>
  );
}

/* ---------------- reveal wrapper ---------------- */

export function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const { ref, inView } = useInView<HTMLDivElement>(0.15);
  return (
    <div
      ref={ref}
      className={cn("reveal", inView && "is-visible", className)}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  );
}

/* ---------------- priority indicator ---------------- */

export function PriorityDot({ priority }: { priority: "HIGH" | "MEDIUM" | "LOW" }) {
  const tone =
    priority === "HIGH" ? "text-error" : priority === "MEDIUM" ? "text-warning" : "text-muted-foreground";
  return (
    <span className={cn("label-sm inline-flex items-center gap-1.5", tone)}>
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-current" />
      {priority}
    </span>
  );
}

/* ---------------- toggle switch ---------------- */

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      data-checked={checked}
      className="toggle-track"
      onClick={() => onChange(!checked)}
    >
      <span className="toggle-thumb" aria-hidden="true" />
    </button>
  );
}
