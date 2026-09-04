import { useEffect, useState } from "react";
import { createFileRoute, Link, redirect, useNavigate } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { Logo } from "@/components/brand";
import { getSession, signIn, useAuth } from "@/lib/auth";
import { toast } from "sonner";

export const Route = createFileRoute("/login")({
  // Signed-in users don't need the auth pages (client-side check; SSR can't
  // read localStorage, so the effect below covers hard loads).
  beforeLoad: () => {
    if (typeof window !== "undefined" && getSession()) {
      throw redirect({ to: "/app/dashboard" });
    }
  },
  head: () => ({
    meta: [
      { title: "Sign In — RecoverAI" },
      { name: "description", content: "Sign in to the RecoverAI payment recovery console." },
      { property: "og:title", content: "Sign In — RecoverAI" },
      { property: "og:description", content: "Access your payment recovery dashboard." },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const session = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Hard-load fallback for signed-in users.
  useEffect(() => {
    if (session) navigate({ to: "/app/dashboard", replace: true });
  }, [session, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await signIn(email, password);
      toast.success("Welcome back", { description: "Signed in successfully" });
      navigate({ to: "/app/dashboard" });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Sign in failed. Please try again.";
      setError(message);
      toast.error("Sign in failed", { description: message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid-bg flex min-h-screen items-center justify-center bg-background px-4 py-16">
      <div className="w-full max-w-md">
        <Link to="/" className="mx-auto block w-fit">
          <Logo />
        </Link>
        <div className="mt-8 rounded-xl bg-surface border border-border p-7 shadow-[0_16px_40px_-20px_rgb(18_20_22/0.6)]">
          <h1 className="headline-md text-foreground">Sign in</h1>
          <p className="mt-2 text-[0.8125rem] text-muted-foreground">
            Enter the recovery console with your merchant credentials.
          </p>
          <form className="mt-7 space-y-4" onSubmit={handleSubmit}>
            <label className="block">
              <span className="label-sm text-faint">Work Email</span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input-field mt-2"
                autoComplete="email"
                autoFocus
              />
            </label>
            <label className="block">
              <span className="label-sm text-faint">Password</span>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-field mt-2"
                autoComplete="current-password"
              />
            </label>
            {error && (
              <p className="text-[0.8125rem] text-error" role="alert">
                {error}
              </p>
            )}
            <button
              type="submit"
              className="btn-primary w-full"
              disabled={loading}
              aria-busy={loading}
            >
              {loading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" aria-hidden="true" />
                  Signing in…
                </>
              ) : (
                "Sign In"
              )}
            </button>
          </form>
          <p className="mt-6 text-center text-[0.75rem] text-muted-foreground">
            No account?{" "}
            <Link to="/signup" className="text-foreground hover:underline">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
