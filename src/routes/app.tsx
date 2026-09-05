import { useCallback, useEffect, useRef, useState } from "react";
import {
  createFileRoute,
  Link,
  Outlet,
  redirect,
  useNavigate,
  useRouterState,
} from "@tanstack/react-router";
import {
  Activity,
  BarChart3,
  FileClock,
  LayoutDashboard,
  Menu,
  Settings,
  ShieldCheck,
  FlaskConical,
} from "lucide-react";
import { LogoMark, LandingLogo } from "@/components/brand";
import { Skeleton } from "@/components/states";
import { Toaster } from "@/components/ui/sonner";
import { CommandPalette } from "@/components/ui/command-palette";
import { ShortcutsDialog } from "@/components/ui/shortcuts-dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { getSession, useAuth } from "@/lib/auth";
import { getAudit, getRecoveries } from "@/lib/api";
import type { AuditEvent, RecoveryPayment } from "@/lib/types";
import { formatINR } from "@/lib/format";

/** G+key navigation map — press G then a letter to jump to a route. */
const G_NAV: Record<string, string> = {
  d: "/app/dashboard",
  r: "/app/recovery",
  a: "/app/analytics",
  s: "/app/simulator",
  u: "/app/audit",
  p: "/app/policies",
  t: "/app/settings",
};

export const Route = createFileRoute("/app")({
  // Client-side guard: in-app navigation is blocked before the shell renders.
  // (Server-side SSR can't see localStorage; the mount gate below covers hard
  // loads without flashing protected content.)
  beforeLoad: () => {
    if (typeof window !== "undefined" && !getSession()) {
      throw redirect({ to: "/login" });
    }
  },
  component: AppLayout,
});

/* -----------------------------------------------------------------------
   Nav items — grouped by section (Operate / Intelligence / Govern / System)
   Labels are always readable on desktop for discoverability.
   ----------------------------------------------------------------------- */
type NavItem = {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" }>;
  group: "operate" | "intelligence" | "govern" | "system";
  iconOnly?: boolean; // true for settings
};

const NAV_ITEMS: NavItem[] = [
  // Operate
  { to: "/app/dashboard", label: "Overview", icon: LayoutDashboard, group: "operate" },
  { to: "/app/recovery", label: "Recovery Queue", icon: Activity, group: "operate" },
  { to: "/app/simulator", label: "Simulator", icon: FlaskConical, group: "operate" },
  // Intelligence
  { to: "/app/analytics", label: "Analytics", icon: BarChart3, group: "intelligence" },
  // Govern
  { to: "/app/audit", label: "Audit Trail", icon: FileClock, group: "govern" },
  { to: "/app/policies", label: "Policies", icon: ShieldCheck, group: "govern" },
  // System
  { to: "/app/settings", label: "Settings", icon: Settings, group: "system", iconOnly: true },
];

/* -----------------------------------------------------------------------
   Neutral skeleton shown until the client can read the session
   ----------------------------------------------------------------------- */
function ShellGate() {
  return (
    <div className="min-h-screen flex items-start justify-center p-4 lg:p-8 bg-app-canvas">
      <div
        className="app-surface w-full max-w-[1728px] overflow-hidden"
        aria-busy="true"
        aria-label="Loading RecoverAI"
      >
        <div className="flex h-[68px] items-center gap-4 border-b border-border px-6">
          <Skeleton className="h-7 w-36" />
          <Skeleton className="h-8 w-80 rounded-full" />
          <div className="ml-auto flex items-center gap-3">
            <Skeleton className="h-9 w-52 rounded-lg" />
            <Skeleton className="h-9 w-9 rounded-full" />
          </div>
        </div>
        <div className="space-y-6 px-6 py-8">
          <Skeleton className="h-10 w-64" />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-3">
            {Array.from({ length: 3 }, (_, i) => (
              <div key={i} className="rounded-xl border border-border bg-surface p-5">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="mt-3 h-6 w-24" />
              </div>
            ))}
          </div>
          <Skeleton className="h-64" />
        </div>
      </div>
    </div>
  );
}

/* -----------------------------------------------------------------------
   Individual desktop nav pill
   ----------------------------------------------------------------------- */
function NavPill({ item }: { item: NavItem }) {
  const routerState = useRouterState();
  const isActive = routerState.location.pathname === item.to ||
    (item.to !== "/app/dashboard" && routerState.location.pathname.startsWith(item.to));

  return (
    <Link
      key={item.to}
      to={item.to}
      className={cn(
        "nav-pill",
        isActive && "nav-pill-active",
      )}
      aria-current={isActive ? "page" : undefined}
    >
      <item.icon
        className={cn("shrink-0", item.iconOnly ? "h-4 w-4" : "h-3.5 w-3.5")}
        aria-hidden="true"
      />
      {!item.iconOnly && <span>{item.label}</span>}
      {item.iconOnly && <span className="sr-only">{item.label}</span>}
    </Link>
  );
}

/* -----------------------------------------------------------------------
   Mobile nav sheet — shows all nav groups with full labels
   ----------------------------------------------------------------------- */
function MobileNavSheet({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const routerState = useRouterState();

  const groupLabel: Record<NavItem["group"], string> = {
    operate: "Operate",
    intelligence: "Intelligence",
    govern: "Govern",
    system: "System",
  };

  const groups = (["operate", "intelligence", "govern", "system"] as const).map((g) => ({
    key: g,
    label: groupLabel[g],
    items: NAV_ITEMS.filter((i) => i.group === g),
  }));

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="bottom"
        className="rounded-t-2xl border-t border-border bg-surface pb-8"
      >
        <SheetHeader className="sr-only">
          <SheetTitle>Navigation</SheetTitle>
        </SheetHeader>
        <nav aria-label="Console navigation" className="mt-4 space-y-5">
          {groups.map(({ key, label, items }) => (
            <div key={key}>
              <p className="label-sm mb-2 px-1 text-muted-foreground">{label}</p>
              <div className="space-y-1">
                {items.map((item) => {
                  const isActive =
                    routerState.location.pathname === item.to ||
                    (item.to !== "/app/dashboard" &&
                      routerState.location.pathname.startsWith(item.to));
                  return (
                    <Link
                      key={item.to}
                      to={item.to}
                      onClick={onClose}
                      className={cn(
                        "flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all",
                        isActive
                          ? "bg-surface-high text-foreground ring-1 ring-border-strong"
                          : "text-muted-foreground hover:bg-surface-high hover:text-foreground",
                      )}
                      aria-current={isActive ? "page" : undefined}
                    >
                      <item.icon
                        className={cn("h-4 w-4 shrink-0", isActive ? "text-foreground" : "text-faint")}
                        aria-hidden="true"
                      />
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
}

/* -----------------------------------------------------------------------
   Top command / search surface
   ----------------------------------------------------------------------- */
function TopSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RecoveryPayment[] | null>(null);
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Global / keyboard shortcut to focus search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.key === "/" || e.key === "k") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  // Debounced search
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults(null);
      setOpen(false);
      return;
    }
    let alive = true;
    const t = setTimeout(() => {
      getRecoveries({ search: q })
        .then((rows) => {
          if (!alive) return;
          setResults(rows.slice(0, 6));
          setOpen(true);
        })
        .catch(() => {
          if (!alive) return;
          setResults(null);
          setOpen(false);
        });
    }, 180);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [query]);

  // Click outside to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const go = (id: string) => {
    setQuery("");
    setOpen(false);
    navigate({ to: "/app/recovery/$id", params: { id } });
  };

  const searching = query.trim().length >= 2;

  return (
    <div ref={containerRef} className="relative hidden sm:block">
      <div className="relative">
        <svg
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="8" />
          <path d="m21 21-4.35-4.35" strokeLinecap="round" />
        </svg>
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => results && setOpen(true)}
          placeholder="Search payments, customers…"
          aria-label="Search payments, customers, and actions"
          role="combobox"
          aria-expanded={open && searching}
          aria-controls="top-search-results"
          aria-autocomplete="list"
          className="w-52 rounded-full border border-border bg-surface py-2 pl-9 pr-10 text-sm text-foreground placeholder-faint outline-none transition-all duration-200 focus:w-72 focus:border-foreground/20 focus:bg-surface-high focus:ring-2 focus:ring-foreground/10"
        />
        <kbd className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded border border-border bg-surface-high px-1.5 py-0.5 font-mono text-[0.625rem] text-faint">
          ⌘K
        </kbd>
      </div>

      {open && searching && (
        <div
          id="top-search-results"
          className="absolute right-0 top-full z-50 mt-2 w-80 overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_24px_64px_-24px_rgba(0,0,0,0.12)]"
          role="listbox"
          aria-label="Search results"
        >
          {results && results.length > 0 ? (
            <ul className="divide-y divide-border">
              {results.map((p) => (
                <li key={p.payment_id}>
                  <button
                    onClick={() => go(p.payment_id)}
                    className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-high"
                  >
                    <span className="min-w-0">
                      <span className="num block truncate text-sm font-medium text-foreground">
                        {p.payment_id}
                      </span>
                      <span className="num block truncate text-xs text-muted-foreground">
                        {p.customer_id} · ₹{(p.amount / 100).toLocaleString("en-IN")}
                      </span>
                    </span>
                    <span
                      className={cn(
                        "chip shrink-0",
                        p.status === "RECOVERED" && "chip-success",
                        p.status === "PROCESSING" && "chip-warning",
                        p.status === "QUEUED" && "chip-neutral",
                        p.status === "SCHEDULED" && "chip-ai",
                        p.status === "HALTED" && "chip-error",
                      )}
                    >
                      {p.status}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="px-4 py-6 text-center">
              <p className="text-sm font-medium text-foreground">No payment found</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Try a payment ID (PAY_xxxxx) or customer ID (cust_xxxxx).
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* -----------------------------------------------------------------------
   Notifications menu
   ----------------------------------------------------------------------- */
function NotificationsMenu() {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    getAudit()
      .then((rows) => alive && setEvents(rows.slice(0, 5)))
      .catch(() => alive && setEvents([]));
    return () => {
      alive = false;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
        aria-expanded={open}
        className="relative grid h-9 w-9 shrink-0 place-items-center rounded-full text-faint transition-all duration-200 hover:bg-surface-high hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <svg
          className="h-4 w-4"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span
          className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-error animate-pulse"
          aria-hidden="true"
        />
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-80 overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_24px_64px_-24px_rgba(0,0,0,0.12)]">
          <p className="label-sm border-b border-border px-4 py-3 text-muted-foreground">
            Recent Activity
          </p>
          {events === null ? (
            <p className="px-4 py-5 text-center text-sm text-muted-foreground">Loading recent activity…</p>
          ) : events.length === 0 ? (
            <p className="px-4 py-5 text-center text-sm text-muted-foreground">
              No activity yet — events appear as recoveries run.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {events.map((e) => (
                <li key={e.id}>
                  <button
                    onClick={() => {
                      setOpen(false);
                      navigate({ to: "/app/recovery/$id", params: { id: e.payment_id } });
                    }}
                    className="block w-full px-4 py-3 text-left transition-all duration-150 hover:bg-surface-high hover:pl-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-inset"
                  >
                    <p className="truncate text-sm text-foreground">{e.summary}</p>
                    <p className="num mt-0.5 text-xs text-muted-foreground">
                      {e.payment_id} · {e.timestamp}
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

/* -----------------------------------------------------------------------
   Profile / account menu
   ----------------------------------------------------------------------- */
function ProfileMenu() {
  const session = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const initial = (session?.email ?? "?").charAt(0).toUpperCase();

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={containerRef} className="relative isolate">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Account menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-lg px-2.5 py-2 transition-colors duration-150 hover:bg-surface-high focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      >
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[#eaeef5] text-[#0c0e14] text-[0.625rem] font-bold shadow-[0_0_0_1px_rgba(255,255,255,0.08)]">
          {initial}
        </span>
        <svg
          className={cn(
            "h-3.5 w-3.5 text-muted-foreground transition-all duration-200",
            open && "rotate-180",
          )}
          aria-hidden="true"
        >
          <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-full z-[60] mt-2 w-64 animate-in fade-in slide-in-from-top-2 duration-200 ease-out rounded-xl bg-surface border border-border shadow-[0_16px_40px_-20px_rgb(18_20_22/0.6)]">
          <div className="border-b border-border px-4 py-3">
            <p className="truncate text-sm font-medium text-foreground">
              {session?.businessName ?? "Merchant"}
            </p>
            <p className="num truncate text-xs text-muted-foreground">{session?.email ?? "—"}</p>
          </div>
          <div className="p-1.5">
            <button
              onClick={() => {
                setOpen(false);
                navigate({ to: "/app/settings" });
              }}
              className="w-full rounded-lg px-2.5 py-2 text-left text-sm text-foreground transition-all duration-150 hover:bg-surface-high hover:pl-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-inset"
            >
              Settings
            </button>
            <button
              onClick={() => {
                setOpen(false);
                import("@/lib/auth").then(({ signOut }) => signOut());
                navigate({ to: "/login" });
              }}
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-error transition-all duration-150 hover:bg-surface-high hover:pl-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-error focus-visible:ring-inset"
            >
              <svg className="h-3.5 w-3.5" aria-hidden="true">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" strokeLinecap="round" strokeLinejoin="round" />
                <polyline points="16 17 21 12 16 7" strokeLinecap="round" strokeLinejoin="round" />
                <line x1="21" y1="12" x2="9" y2="12" strokeLinecap="round" />
              </svg>
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* -----------------------------------------------------------------------
   Health / status indicator
   ----------------------------------------------------------------------- */
function HealthIndicator() {
  return (
    <span
      className="hidden rounded-full border border-[rgb(52_211_153/0.25)] bg-[rgb(52_211_153/0.1)] px-2.5 py-1 font-mono text-[0.6875rem] font-medium tracking-wide text-[#34d399] md:inline-flex md:items-center md:gap-1.5"
      title="Connected to Razorpay Test Mode"
    >
      <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points="22 4 12 14.01 9 11.01" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Operational
    </span>
  );
}

/* -----------------------------------------------------------------------
   Main app layout — floating surface architecture
   ----------------------------------------------------------------------- */
function AppLayout() {
  const session = useAuth();
  const navigate = useNavigate();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const pendingG = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Session lives in localStorage — only readable after hydration.
  useEffect(() => {
    setReady(true);
  }, []);

  useEffect(() => {
    if (ready && !session) navigate({ to: "/login", replace: true });
  }, [ready, session, navigate]);

  // Listen for custom event from command palette to open shortcuts
  useEffect(() => {
    const handler = () => setShortcutsOpen(true);
    document.addEventListener("open-shortcuts", handler);
    return () => document.removeEventListener("open-shortcuts", handler);
  }, []);

  // Global keyboard shortcuts: ? for help, / for command palette, G+key for navigation
  const handleGlobalKeys = useCallback(
    (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement).isContentEditable) {
        return;
      }
      if (document.querySelector("[data-radix-dialog-overlay]")) {
        return;
      }

      if (e.key === "?" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        setShortcutsOpen(true);
        return;
      }

      if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        document.dispatchEvent(new CustomEvent("open-command-palette"));
        return;
      }

      if (e.key.toLowerCase() === "g" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        if (pendingG.current) clearTimeout(pendingG.current);
        pendingG.current = setTimeout(() => {
          pendingG.current = null;
        }, 800);
        return;
      }

      if (pendingG.current) {
        const path = G_NAV[e.key.toLowerCase()];
        if (path) {
          e.preventDefault();
          clearTimeout(pendingG.current);
          pendingG.current = null;
          navigate({ to: path });
        } else {
          clearTimeout(pendingG.current);
          pendingG.current = null;
        }
      }
    },
    [navigate],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleGlobalKeys);
    return () => {
      document.removeEventListener("keydown", handleGlobalKeys);
      if (pendingG.current) clearTimeout(pendingG.current);
    };
  }, [handleGlobalKeys]);

  if (!ready || !session) {
    return <ShellGate />;
  }

  return (
    <>
      {/* Skip to main content */}
      <a
        href="#content"
        className="sr-only focus:not-sr-only focus:fixed focus:inset-x-0 focus:top-0 focus:z-[100] focus:bg-[var(--color-background)] focus:py-3 focus:text-center focus:text-sm focus:font-medium focus:text-foreground focus:outline-none focus:ring-2 focus:ring-foreground"
      >
        Skip to content
      </a>

      {/* Outer canvas */}
      <div className="min-h-screen app-canvas p-2 sm:p-3 lg:p-4">
        {/* Floating app surface */}
        <div className="app-surface mx-auto w-full max-w-[1728px] overflow-hidden">
          {/* ---------- Integrated top nav ---------- */}
          <header className="relative z-20 flex items-center gap-3 px-4 py-3 sm:px-5 lg:px-6 lg:gap-4 liquid-glass overflow-visible">
            {/* Mobile: hamburger + logo */}
            <button
              onClick={() => setMobileNavOpen(true)}
              aria-label="Open navigation"
              className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-muted-foreground transition-all duration-200 hover:bg-surface-high hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background lg:hidden"
            >
              <Menu className="h-4 w-4" aria-hidden="true" />
            </button>

            {/* Logo */}
            <Link
              to="/app/dashboard"
              className="flex items-center gap-2 rounded-xl px-1 py-1 transition-all duration-200 hover:bg-surface-high focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground"
            >
              <LandingLogo size="app" />
            </Link>

            {/* Desktop segmented nav cluster */}
            <nav
              aria-label="Console navigation"
              className="hidden items-center gap-1 lg:flex"
            >
              {/* Operate group */}
              {NAV_ITEMS.filter((i) => i.group === "operate").map((item, idx) => (
                <NavPill key={item.to} item={item} />
              ))}
              <span className="nav-divider" aria-hidden="true" />
              {/* Intelligence */}
              {NAV_ITEMS.filter((i) => i.group === "intelligence").map((item) => (
                <NavPill key={item.to} item={item} />
              ))}
              <span className="nav-divider" aria-hidden="true" />
              {/* Govern */}
              {NAV_ITEMS.filter((i) => i.group === "govern").map((item) => (
                <NavPill key={item.to} item={item} />
              ))}
              <span className="nav-divider" aria-hidden="true" />
              {/* System */}
              {NAV_ITEMS.filter((i) => i.group === "system").map((item) => (
                <NavPill key={item.to} item={item} />
              ))}
            </nav>

            {/* Right actions */}
            <div className="ml-auto flex items-center gap-1 sm:gap-2">
              <TopSearch />
              <div className="hidden sm:block">
                <NotificationsMenu />
              </div>
              <ProfileMenu />
            </div>
          </header>

          {/* ---------- Content area ---------- */}
          <main
            id="content"
            className="relative px-5 pb-8 pt-2 sm:px-8 lg:px-10"
          >
            <CommandPalette />
            <ShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
            <div className="relative z-10">
              <Outlet />
            </div>
          </main>

          {/* Toaster */}
          <Toaster
            position="bottom-right"
            toastOptions={{
              duration: 4000,
              style: {
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                color: "var(--color-foreground)",
              },
            }}
          />
        </div>
      </div>

      {/* Mobile nav sheet */}
      <MobileNavSheet open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
    </>
  );
}
