import { createFileRoute, Link, redirect, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { LandingLogo } from "@/components/brand";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/onboarding")({
  beforeLoad: () => {
    if (typeof window !== "undefined" && !window.localStorage.getItem("recoverai.session")) {
      throw redirect({ to: "/login" });
    }
  },
  head: () => ({
    meta: [
      { title: "Onboarding — RecoverAI" },
      { name: "description", content: "Set up RecoverAI to start recovering failed payments." },
    ],
  }),
  component: OnboardingPage,
});

const STEPS = [
  {
    title: "Welcome to RecoverAI",
    body: "RecoverAI monitors your failed payments, decides how to recover them, and executes safely with policy guardrails.",
  },
  {
    title: "Connect Razorpay",
    body: "Use Razorpay Test Mode API keys. Your secret is encrypted at rest and never displayed again after submission.",
  },
  {
    title: "Verify Connection",
    body: "Run a connection test to confirm your keys work. We never send live requests during this step.",
  },
  {
    title: "Webhook",
    body: "Configure the webhook URL in your Razorpay dashboard. RecoverAI verifies each event signature before processing.",
  },
  {
    title: "You're ready",
    body: "Your dashboard will populate as Razorpay delivers failed-payment events. You can revisit this setup from Settings.",
  },
];

function OnboardingPage() {
  const session = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [skipped, setSkipped] = useState(false);

  const finish = () => {
    window.localStorage.setItem("recoverai.onboarded", "1");
    navigate({ to: "/app/dashboard" });
  };

  if (typeof window !== "undefined" && !session) {
    navigate({ to: "/login" });
    return null;
  }

  return (
    <div className="grid-bg flex min-h-screen items-center justify-center bg-background px-4 py-16">
      <div className="w-full max-w-lg">
        <Link to="/" className="mx-auto block w-fit">
          <LandingLogo size="auth" />
        </Link>
        <div className="mt-8 rounded-xl bg-surface border border-border p-7 shadow-[0_16px_40px_-20px_rgb(18_20_22/0.6)]">
          <div className="mb-6 flex items-center justify-between">
            <span className="label-sm text-muted-foreground">
              Step {step + 1} of {STEPS.length}
            </span>
            <button
              type="button"
              onClick={() => {
                setSkipped(true);
                finish();
              }}
              className="text-[0.75rem] text-muted-foreground hover:text-foreground"
            >
              Skip
            </button>
          </div>
          <div className="mb-6 h-1 w-full overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className="h-full bg-ai transition-all"
              style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
            />
          </div>
          <h1 className="headline-md text-foreground">{STEPS[step]!.title}</h1>
          <p className="mt-3 text-[0.8125rem] text-muted-foreground">{STEPS[step]!.body}</p>
          {session && (
            <p className="mt-4 text-[0.75rem] text-muted-foreground">
              Signed in as <span className="text-foreground">{session?.email ?? "unknown"}</span>
              {(session?.businessName ? ` — ${session.businessName}` : "") as string}
            </p>
          )}
          <div className="mt-7 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
              className="btn-ghost"
            >
              Back
            </button>
            {step < STEPS.length - 1 ? (
              <button type="button" onClick={() => setStep((s) => s + 1)} className="btn-primary">
                Continue
              </button>
            ) : (
              <button type="button" onClick={finish} className="btn-primary">
                Go to dashboard
              </button>
            )}
          </div>
        </div>
        {skipped && (
          <p className="mt-4 text-center text-[0.75rem] text-muted-foreground">
            Onboarding skipped. You can resume from Settings.
          </p>
        )}
      </div>
    </div>
  );
}
