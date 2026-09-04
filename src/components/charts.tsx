import { useId } from "react";
import { cn } from "@/lib/utils";
import { useInView } from "@/lib/hooks";
import { formatLakh } from "@/lib/format";

/* ------------------------------------------------------------------ */
/* Kinetic line chart — thin 1.5px strokes, gradient area, draw-in     */
/* ------------------------------------------------------------------ */

function buildPath(values: number[], width: number, height: number, pad = 4) {
  if (values.length === 0) return "";
  if (values.length === 1) {
    const mid = height / 2;
    return `M${pad},${mid} L${width - pad},${mid}`;
  }
  const finite = values.filter((v) => Number.isFinite(v));
  const max = (finite.length > 0 ? Math.max(...finite) : 0) * 1.08;
  const min = (finite.length > 0 ? Math.min(...finite) : 0) * 0.9;
  const range = max - min || 1;
  const step = (width - pad * 2) / (values.length - 1);
  return values
    .map((v, i) => {
      const safe = Number.isFinite(v) ? v : min;
      const x = pad + i * step;
      const y = height - pad - ((safe - min) / range) * (height - pad * 2);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function LineChart({
  series,
  baseline,
  labels,
  height = 180,
  className,
}: {
  series: number[];
  baseline?: number[];
  labels?: string[];
  height?: number;
  className?: string;
}) {
  const gradientId = useId();
  const { ref, inView } = useInView<HTMLDivElement>(0.3);
  const width = 560;

  const line = buildPath(series, width, height);
  const area = `${line} L${width - 4},${height} L4,${height} Z`;
  const baseLine = baseline ? buildPath(baseline, width, height) : null;

  return (
    <div ref={ref} className={cn("w-full", className)}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        role="img"
        aria-label="Recovered revenue over time"
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--chart-foreground)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--chart-foreground)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* horizontal hairlines */}
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1="4"
            x2={width - 4}
            y1={height * f}
            y2={height * f}
            stroke="rgba(23,25,27,0.06)"
            strokeWidth="1"
          />
        ))}

        <path d={area} fill={`url(#${gradientId})`} opacity={inView ? 1 : 0} style={{ transition: "opacity 1.2s ease 0.5s" }} />

        {baseLine && (
          <path
            d={baseLine}
            fill="none"
            stroke="rgba(87,92,97,0.45)"
            strokeWidth="1.25"
            strokeDasharray="4 5"
            pathLength={1}
            style={{
              strokeDashoffset: inView ? 0 : 1,
              transition: "stroke-dashoffset 1.4s cubic-bezier(0.22,1,0.36,1)",
            }}
          />
        )}

        <path
          d={line}
          fill="none"
          stroke="var(--chart-foreground)"
          strokeWidth="1.5"
          strokeLinecap="round"
          pathLength={1}
          style={{
            strokeDasharray: 1,
            strokeDashoffset: inView ? 0 : 1,
            transition: "stroke-dashoffset 1.6s cubic-bezier(0.22,1,0.36,1)",
          }}
        />
      </svg>
      {labels && (
        <div className="mt-2 flex justify-between label-sm text-faint">
          {labels.map((l) => (
            <span key={l}>{l}</span>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Horizontal comparison bars                                          */
/* ------------------------------------------------------------------ */

export function CompareBars({
  staticValue,
  aiValue,
  format,
  className,
}: {
  staticValue: number;
  aiValue: number;
  format?: (n: number) => string;
  className?: string;
}) {
  const { ref, inView } = useInView<HTMLDivElement>(0.4);
  const fmt = format ?? ((n: number) => formatLakh(n));
  const max = Math.max(staticValue, aiValue);

  return (
    <div ref={ref} className={cn("space-y-6", className)}>
      <div>
        <div className="flex items-baseline justify-between">
          <span className="label-sm text-muted-foreground">Static Retry</span>
          <span className="num text-lg text-muted-foreground">{fmt(staticValue)}</span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-high">
          <div
            className="h-full rounded-full bg-muted-foreground/60"
            style={{
              width: inView ? `${(staticValue / max) * 100}%` : "0%",
              transition: "width 1.1s cubic-bezier(0.22,1,0.36,1) 0.1s",
            }}
          />
        </div>
      </div>
      <div>
        <div className="flex items-baseline justify-between">
          <span className="label-sm text-ai">RecoverAI</span>
          <span className="num text-lg text-foreground">{fmt(aiValue)}</span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-high">
          <div
            className="h-full rounded-full"
            style={{
              width: inView ? `${(aiValue / max) * 100}%` : "0%",
              background: "linear-gradient(90deg, #9498a6, #6b7080)",
              boxShadow: "0 0 8px rgba(255,255,255,0.06)",
              transition: "width 1.3s cubic-bezier(0.22,1,0.36,1) 0.25s",
            }}
          />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Simple horizontal bar list (analytics breakdowns)                   */
/* ------------------------------------------------------------------ */

export function BarList({
  rows,
  formatValue,
  accent = "#9498a6",
}: {
  rows: { label: string; value: number; hint?: string }[];
  formatValue: (n: number) => string;
  accent?: string;
}) {
  const { ref, inView } = useInView<HTMLDivElement>(0.25);
  const max = Math.max(...rows.map((r) => r.value), 0);
  return (
    <div ref={ref} className="space-y-4">
      {rows.map((row, i) => (
        <div key={row.label}>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm text-foreground">{row.label}</span>
            <span className="num text-sm text-muted-foreground">
              {formatValue(row.value)}
              {row.hint && <span className="ml-2 text-faint">{row.hint}</span>}
            </span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-high">
            <div
              className="h-full rounded-full"
              style={{
                width: inView ? `${(row.value / max) * 100}%` : "0%",
                background: accent,
                opacity: 1 - i * 0.12,
                transition: `width 0.9s cubic-bezier(0.22,1,0.36,1) ${i * 90}ms`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
