import { useEffect, useState } from "react";
import { Link, useNavigate, useRouter } from "@tanstack/react-router";
import { Menu, X } from "lucide-react";
import { Logo, LandingLogo } from "./brand";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";

const NAV_LINKS = [
  { label: "Product", to: "/", hash: "product" },
  { label: "How It Works", to: "/", hash: "how-it-works" },
  { label: "Simulator", to: "/", hash: "simulator" },
] as const;

export function SiteNavbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const session = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const goDashboard = () => {
    setOpen(false);
    navigate({ to: session ? "/app/dashboard" : "/login" });
  };

  return (
    <header
      className={cn(
        "liquid-glass-nav-fixed transition-all duration-300",
        "liquid-glass"
      )}
    >
      <nav className="container-grid flex h-16 items-center justify-between overflow-x-hidden" aria-label="Main">
        <Link to="/" aria-label="RecoverAI home" onClick={() => setOpen(false)}>
          <LandingLogo />
        </Link>

        <div className="nav-track hidden md:flex">
          {NAV_LINKS.map((l) => (
            <a
              key={l.label}
              href={`#${l.hash}`}
              className="nav-pill"
            >
              {l.label}
            </a>
          ))}
          <button onClick={goDashboard} className="nav-pill">
            Dashboard
          </button>
        </div>

        <div className="hidden items-center gap-3 md:flex">
          {session ? (
            <Link to="/app/dashboard" className="btn-primary !py-2">
              Open Dashboard
            </Link>
          ) : (
            <>
              <Link
                to="/login"
                className="px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
              >
                Sign In
              </Link>
              <Link to="/signup" className="btn-primary !py-2">
                Get Started
              </Link>
            </>
          )}
        </div>

        <button
          className="grid h-10 w-10 place-items-center rounded-md border border-border-strong text-foreground md:hidden"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
        >
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </nav>

      {open && (
        <div className="glass border-t border-border md:hidden">
          <div className="container-grid flex flex-col gap-1 py-4">
            {NAV_LINKS.map((l) => (
              <a
                key={l.label}
                href={`#${l.hash}`}
                onClick={() => setOpen(false)}
                className="rounded-md px-3 py-2.5 text-sm text-muted-foreground hover:bg-surface-high hover:text-foreground"
              >
                {l.label}
              </a>
            ))}
            <button
              onClick={goDashboard}
              className="rounded-md px-3 py-2.5 text-left text-sm text-muted-foreground hover:bg-surface-high hover:text-foreground"
            >
              Dashboard
            </button>
            <div className="mt-3 flex gap-3 border-t border-border pt-4">
              {session ? (
                <Link to="/app/dashboard" className="btn-primary flex-1 !py-2.5" onClick={() => setOpen(false)}>
                  Open Dashboard
                </Link>
              ) : (
                <>
                  <Link to="/login" className="btn-ghost flex-1 !py-2.5" onClick={() => setOpen(false)}>
                    Sign In
                  </Link>
                  <Link to="/signup" className="btn-primary flex-1 !py-2.5" onClick={() => setOpen(false)}>
                    Get Started
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-background">
      <div className="container-grid flex flex-col gap-6 py-10 md:flex-row md:items-center md:justify-between">
        <div>
          <Logo />
          <p className="mt-3 text-xs text-muted-foreground">
            © 2026 RecoverAI. All rights reserved. High-fidelity payment recovery systems.
          </p>
        </div>
        <nav className="flex flex-wrap gap-x-8 gap-y-2" aria-label="Footer">
          {[
            { label: "Privacy Policy", href: "/privacy" },
            { label: "Terms of Service", href: "/terms" },
            { label: "Security", href: "/security" },
            { label: "Status", href: "/status" },
          ].map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              {l.label}
            </a>
          ))}
        </nav>
      </div>
    </footer>
  );
}
