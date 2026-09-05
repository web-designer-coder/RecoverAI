import { useEffect, useState } from "react";
import { createFileRoute, Link, redirect, useNavigate } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { LandingLogo } from "@/components/brand";
import { getSession, signUp, useAuth } from "@/lib/auth";
import { toast } from "sonner";

export const Route = createFileRoute("/signup")({
  beforeLoad: () => {
    if (typeof window !== "undefined" && getSession()) {
      throw redirect({ to: "/app/dashboard" });
    }
  },
  head: () => ({
    meta: [
      { title: "Create Account — RecoverAI" },
      { name: "description", content: "Create a RecoverAI account and start recovering failed payments." },
      { property: "og:title", content: "Create Account — RecoverAI" },
      { property: "og:description", content: "Start recovering failed payment revenue with AI." },
    ],
  }),
  component: SignupPage,
});

function SignupPage() {
  const navigate = useNavigate();
  const session = useAuth();
  const [business, setBusiness] = useState("");
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
      await signUp(business, email, password);
      toast.success("Account created", { description: "Welcome to RecoverAI" });
      navigate({ to: "/app/dashboard" });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Sign up failed. Please try again.";
      setError(message);
      toast.error("Sign up failed", { description: message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid-bg flex min-h-screen items-center justify-center bg-background px-4 py-16">
      <div className="w-full max-w-md">
        <Link to="/" className="mx-auto block w-fit">
          <LandingLogo size="auth" />
        </Link>
        <div className="mt-8 rounded-xl bg-surface border border-border p-7 shadow-[0_16px_40px_-20px_rgb(18_20_22/0.6)]">
          <h1 className="headline-md text-foreground">Create account</h1>
          <p className="mt-2 text-[0.8125rem] text-muted-foreground">
            Create your account to start recovering failed payments.
          </p>
          <form className="mt-7 space-y-4" onSubmit={handleSubmit}>
            {[
              { label: "Business Name", value: business, set: setBusiness, type: "text" },
              { label: "Work Email", value: email, set: setEmail, type: "email" },
              { label: "Password", value: password, set: setPassword, type: "password" },
            ].map((f) => (
              <label key={f.label} className="block">
                <span className="label-sm text-faint">{f.label}</span>
                <input
                  type={f.type}
                  required
                  value={f.value}
                  onChange={(e) => f.set(e.target.value)}
                  className="input-field mt-2"
                  autoComplete={f.type === "email" ? "email" : f.type === "password" ? "new-password" : "name"}
                />
              </label>
            ))}
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
                  Creating account…
                </>
              ) : (
                "Create Account"
              )}
            </button>
          </form>
          <p className="mt-6 text-center text-[0.75rem] text-muted-foreground">
            Already have an account?{" "}
            <Link to="/login" className="text-foreground hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
