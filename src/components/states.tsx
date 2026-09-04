import { Component, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import { AlertCircle, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

/* ---------------- loading skeleton ---------------- */

/** Shimmer-free skeleton block — quiet, tonal, matches panel language. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-surface-high", className)} aria-hidden="true" />;
}

/** Skeleton for a page-level data load. `variant` controls layout: "dashboard" (default) = 6-metric strip + panels, "content" = 4-metric + single panel, "table" = 4-metric + list rows, "list" = header + stacked cards. */
export function PageLoading({ label, variant = "dashboard" }: { label?: string; variant?: "dashboard" | "content" | "table" | "list" }) {
  return (
    <div className="space-y-6" role="status" aria-live="polite">
      {label && <p className="label-sm text-faint">{label}</p>}
      <Skeleton className="h-8 w-48" />
      {variant === "dashboard" && (
        <>
          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-3 xl:grid-cols-6">
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} className="bg-surface p-5">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="mt-3 h-6 w-24" />
              </div>
            ))}
          </div>
          <div className="grid gap-6 lg:grid-cols-3">
            <Skeleton className="h-64 lg:col-span-2" />
            <Skeleton className="h-64" />
          </div>
        </>
      )}
      {variant === "content" && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="panel p-5">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="mt-3 h-6 w-24" />
              </div>
            ))}
          </div>
          <Skeleton className="h-64" />
        </>
      )}
      {variant === "table" && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className="panel p-5">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="mt-3 h-6 w-24" />
              </div>
            ))}
          </div>
          <div className="panel divide-y divide-border">
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="flex items-center gap-4 p-4">
                <Skeleton className="h-4 w-4 shrink-0" />
                <Skeleton className="h-4 flex-1" />
                <Skeleton className="h-4 w-24" />
              </div>
            ))}
          </div>
        </>
      )}
      {variant === "list" && (
        <div className="space-y-3">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------------- empty state ---------------- */

export function EmptyState({
  icon: Icon = Inbox,
  title,
  copy,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  copy: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-14 text-center", className)}>
      <span className="grid h-11 w-11 place-items-center rounded-full border border-border bg-surface-low">
        <Icon className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
      </span>
      <p className="mt-4 text-sm font-semibold text-foreground">{title}</p>
      <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">{copy}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/* ---------------- error / not-found state ---------------- */

export function ErrorState({
  title = "Couldn't load this view",
  copy,
  retry,
}: {
  title?: string;
  copy: string;
  retry?: () => void;
}) {
  return (
    <EmptyState
      icon={AlertCircle}
      title={title}
      copy={copy}
      action={
        <div className="flex items-center gap-3">
          {retry && (
            <button className="btn-primary !py-2" onClick={retry}>
              Try again
            </button>
          )}
          <Link to="/app/dashboard" className="btn-ghost !py-2">
            Back to Overview
          </Link>
        </div>
      }
    />
  );
}

/* ---------------- error boundary (chart / widget crash guard) ---------------- */

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

/** Lightweight error boundary — catches render crashes in child components
 *  (e.g. chart libraries) and shows a safe fallback instead of a white screen. */
export class ChartErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  override componentDidCatch(error: Error) {
    console.error("[ChartErrorBoundary]", error);
  }

  override render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <EmptyState
            icon={AlertCircle}
            title="Chart unavailable"
            copy="This visualization couldn't render. The data is still accessible in other sections."
          />
        )
      );
    }
    return this.props.children;
  }
}
