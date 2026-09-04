import { useEffect, useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Bell, CheckCircle2, ChevronDown, LogOut, Search } from "lucide-react";
import { getAudit, getRecoveries } from "@/lib/api";
import type { AuditEvent, RecoveryPayment } from "@/lib/types";
import { formatINR, formatDateTime } from "@/lib/format";
import { signOut, useAuth } from "@/lib/auth";
import { StatusChip } from "@/components/primitives";
import { cn } from "@/lib/utils";

/**
 * Console top bar: global payment search, system health, notifications,
 * merchant profile. Popovers are lightweight local state — no new deps.
 */

function useClickOutside(onClose: () => void) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    const el = ref.current;
    const handler = (e: MouseEvent | FocusEvent) => {
      if (!el.contains(e.target as Node)) onClose();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("focusin", handler);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("focusin", handler);
      document.removeEventListener("keydown", key);
    };
  }, [onClose]);
  return ref;
}

/* ---------------- global payment search ---------------- */

function GlobalSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RecoveryPayment[] | null>(null);
  const [open, setOpen] = useState(false);

  const close = () => setOpen(false);
  const ref = useClickOutside(close);

  // Debounced lookup against the recovery queue by payment/customer/failure text.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults(null);
      setOpen(false);
      return;
    }
    let alive = true;
    const t = setTimeout(() => {
      getRecoveries({ search: q }).then((rows) => {
        if (!alive) return;
        setResults(rows.slice(0, 6));
        setOpen(true);
      });
    }, 180);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [query]);

  const go = (id: string) => {
    setQuery("");
    setOpen(false);
    navigate({ to: "/app/recovery/$id", params: { id } });
  };

  const searching = query.trim().length >= 2;

  return (
    <div ref={ref} className="relative min-w-0 flex-1 sm:max-w-md">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" aria-hidden="true" />
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results && setOpen(true)}
        placeholder="Search payment or customer ID"
        aria-label="Search payments by payment ID or customer ID"
        role="combobox"
        aria-expanded={open && searching}
        className="input-field !rounded-lg !py-2 !pl-9 !pr-3 !text-sm"
      />
      {open && searching && (
        <div
          className="absolute inset-x-0 top-full z-50 mt-2 animate-in fade-in slide-in-from-top-2 duration-200 ease-out overflow-hidden rounded-xl bg-surface border border-border shadow-[0_16px_40px_-20px_rgb(18_20_22/0.6)]"
          role="listbox"
          aria-label="Payment search results"
        >
          {results && results.length > 0 ? (
            <ul className="divide-y divide-border">
              {results.map((p) => (
                <li key={p.payment_id}>
                  <button
                    onClick={() => go(p.payment_id)}
                    className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-high/50"
                  >
                    <span className="min-w-0">
                      <span className="num block truncate text-sm font-medium text-foreground">{p.payment_id}</span>
                      <span className="num block truncate text-xs text-faint">
                        {p.customer_id} · {formatINR(p.amount)}
                      </span>
                    </span>
                    <StatusChip status={p.status} />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="px-4 py-5 text-center">
              <p className="text-sm font-medium text-foreground">No payment found</p>
              <p className="mt-1 text-xs text-muted-foreground">
                No results for "{query.trim()}". Try a payment ID (PAY_xxxxx) or a customer ID (cust_xxxxx).
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- notifications ---------------- */

function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const navigate = useNavigate();

  const close = () => setOpen(false);
  const ref = useClickOutside(close);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    getAudit().then((rows) => alive && setEvents(rows.slice(0, 5)));
    return () => {
      alive = false;
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
        aria-expanded={open}
        className="relative grid h-11 w-11 place-items-center rounded-lg text-muted-foreground transition-all duration-200 hover:bg-surface-high hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <Bell className="h-4 w-4 transition-transform duration-200 group-hover:rotate-12" />
        <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-error animate-pulse" aria-hidden="true" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 animate-in fade-in slide-in-from-top-2 duration-200 ease-out overflow-hidden rounded-xl bg-surface border border-border shadow-[0_16px_40px_-20px_rgb(18_20_22/0.6)]">
          <p className="label-sm border-b border-border px-4 py-3 text-muted-foreground">Recent Activity</p>
          {events === null ? (
            <p className="px-4 py-5 text-center text-sm text-muted-foreground">Loading recent activity…</p>
          ) : events.length === 0 ? (
            <p className="px-4 py-5 text-center text-sm text-muted-foreground">No activity yet — events appear as recoveries run.</p>
          ) : (
            <ul className="divide-y divide-border">
              {events.map((e) => (
                <li key={e.id}>
                  <button
                    onClick={() => {
                      close();
                      navigate({ to: "/app/recovery/$id", params: { id: e.payment_id } });
                    }}
                    className="block w-full px-4 py-3 text-left transition-all duration-150 hover:bg-surface-high/50 hover:pl-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-inset"
                  >
                    <p className="truncate text-sm text-foreground">{e.summary}</p>
                    <p className="num mt-0.5 text-xs text-faint">
                      {e.payment_id} · {formatDateTime(e.timestamp)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------- merchant profile ---------------- */

function ProfileMenu() {
  const session = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const close = () => setOpen(false);
  const ref = useClickOutside(close);

  const initial = (session?.email ?? "?").charAt(0).toUpperCase();

  return (
    <div ref={ref} className="relative isolate">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Account menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-lg px-2.5 py-2 transition-colors duration-150 hover:bg-surface-high focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-surface text-[0.625rem] font-bold text-background">
          {initial}
        </span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 text-muted-foreground transition-all duration-200",
            open && "rotate-180",
          )}
          aria-hidden="true"
        />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-[60] mt-2 w-64 animate-in fade-in slide-in-from-top-2 duration-200 ease-out overflow-visible rounded-xl bg-surface border border-border shadow-[0_16px_40px_-20px_rgb(18_20_22/0.6)] pointer-events-auto">
          <div className="border-b border-border px-4 py-3">
            <p className="truncate text-sm font-medium text-foreground">{session?.businessName ?? "Merchant"}</p>
            <p className="num truncate text-xs text-muted-foreground">{session?.email ?? "—"}</p>
          </div>
          <div className="p-1.5">
            <button
              onClick={() => {
                close();
                navigate({ to: "/app/settings" });
              }}
              className="w-full rounded-lg px-2.5 py-2 text-left text-sm text-foreground transition-all duration-150 hover:bg-surface-high hover:pl-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-inset"
            >
              Settings
            </button>
            <button
              onClick={() => {
                close();
                signOut();
                navigate({ to: "/" });
              }}
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-error transition-all duration-150 hover:bg-surface-high hover:pl-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error focus-visible:ring-inset"
            >
              <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- health indicator ---------------- */

export function HealthIndicator() {
  return (
    <span
      className="chip chip-success"
      title="Connected to Razorpay Test Mode"
    >
      <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
      <span className="hidden sm:inline">Operational</span>
      <span className="sr-only sm:hidden">System operational</span>
    </span>
  );
}

/* ---------------- top bar ---------------- */

export function TopBar({
  onOpenNav,
  className,
  hamburgerRef,
}: {
  onOpenNav?: () => void;
  className?: string;
  hamburgerRef?: React.RefObject<HTMLButtonElement | null>;
}) {
  return (
    <header
      className={cn(
        "sticky top-0 z-40 flex flex-wrap items-center gap-3 border-b border-border bg-background/80 backdrop-blur-xl px-4 py-3 sm:px-6 lg:px-8",
        className,
      )}
    >
      {onOpenNav && (
        <button
          ref={hamburgerRef}
          onClick={onOpenNav}
          aria-label="Open navigation"
          className="grid h-11 w-11 shrink-0 place-items-center rounded-lg text-foreground transition-all duration-200 hover:bg-surface-high hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background lg:hidden"
        >
          <span className="sr-only">Open navigation</span>
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
          </svg>
        </button>
      )}
      <GlobalSearch />
      <div className="ml-auto flex items-center gap-3">
        <HealthIndicator />
        <NotificationsMenu />
        <ProfileMenu />
      </div>
    </header>
  );
}
