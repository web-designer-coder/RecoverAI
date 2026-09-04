import { useEffect, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { KeyRound, LogOut, TriangleAlert, Loader2, CheckCircle2, XCircle, Wifi, WifiOff, RotateCcw } from "lucide-react";
import { signOut, useAuth } from "@/lib/auth";
import { api, getMerchantProfile } from "@/lib/api";
import type { MerchantProfile } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Toggle } from "@/components/primitives";
import { toast } from "sonner";

export const Route = createFileRoute("/app/settings")({
  head: () => ({
    meta: [
      { title: "Settings — RecoverAI" },
      { name: "description", content: "Account, workspace and notification settings for the RecoverAI console." },
      { property: "og:title", content: "Settings — RecoverAI" },
      { property: "og:description", content: "Manage your RecoverAI workspace." },
    ],
  }),
  component: SettingsPage,
});

const NOTIFICATION_PREFS = [
  { key: "recoveries", label: "Recovery outcomes", copy: "When a recovery settles or is halted" },
  { key: "escalations", label: "Policy escalations", copy: "High-value payments awaiting operator approval" },
  { key: "dailyDigest", label: "Daily digest", copy: "Morning summary of revenue at risk and recoveries" },
] as const;

function SettingsPage() {
  const session = useAuth();
  const navigate = useNavigate();
  const [prefs, setPrefs] = useState<Record<(typeof NOTIFICATION_PREFS)[number]["key"], boolean>>({
    recoveries: true,
    escalations: true,
    dailyDigest: false,
  });

  // Merchant profile from backend (source of truth)
  const [profile, setProfile] = useState<MerchantProfile | null>(null);

  // Razorpay integration state
  const [keyId, setKeyId] = useState("");
  const [keySecret, setKeySecret] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [razorpayConnected, setRazorpayConnected] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [webhookStatus, setWebhookStatus] = useState<{ configured: boolean; lastVerified: string | null } | null>(null);
  const [savingCredentials, setSavingCredentials] = useState(false);
  const [saveError, setSaveError] = useState("");

  // Fetch profile, webhook + integration status on load
  useEffect(() => {
    if (session) {
      getMerchantProfile().then(setProfile).catch(() => {});
      fetchWebhookStatus();
      fetchRazorpayIntegration();
    }
  }, [session]);

  const fetchWebhookStatus = async () => {
    try {
      const status = await api.getRazorpayWebhookStatus();
      setWebhookStatus(status);
    } catch {
      // Ignore errors - webhook status is optional
    }
  };

  const fetchRazorpayIntegration = async () => {
    try {
      const integration = await api.getRazorpayIntegration();
      if (integration.configured) {
        setRazorpayConnected(true);
        if (integration.keyId) {
          setKeyId(integration.keyId);
        }
      } else {
        setRazorpayConnected(false);
      }
    } catch {
      // Ignore errors - treat as not connected
    }
  };

  const handleSaveCredentials = async () => {
    if (!keyId || !keySecret) {
      setSaveError("Please enter both Key ID and Key Secret");
      toast.error("Missing credentials", { description: "Please enter both Key ID and Key Secret" });
      return;
    }
    setSaveError("");
    setSavingCredentials(true);
    try {
      await api.updateMerchantRazorpayCredentials(keyId, keySecret);
      setRazorpayConnected(true);
      setKeySecret(""); // Clear secret from UI after successful save
      setSaveError("");
      toast.success("Credentials saved", { description: "Razorpay integration connected" });
      // Fetch updated webhook status
      fetchWebhookStatus();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to save credentials";
      setSaveError(message);
      toast.error("Save failed", { description: message });
    } finally {
      setSavingCredentials(false);
    }
  };

  const handleTestConnection = async () => {
    if (!razorpayConnected) {
      setTestResult({ success: false, message: "Please save credentials first" });
      toast.error("Not connected", { description: "Please save credentials first" });
      return;
    }
    setTestingConnection(true);
    setTestResult(null);
    toast.info("Testing connection…", { description: "Verifying Razorpay credentials" });
    try {
      const result = await api.testRazorpayConnection();
      setTestResult({ success: true, message: result.message });
      toast.success("Connection successful", { description: result.message });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Connection test failed";
      setTestResult({ success: false, message });
      toast.error("Connection failed", { description: message });
    } finally {
      setTestingConnection(false);
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="headline-md text-foreground">Settings</h1>
        <p className="mt-1.5 text-[0.8125rem] text-muted-foreground">
          Merchant profile, integrations and notification preferences.
        </p>
      </header>

      {/* merchant profile — sourced from GET /api/merchants/me */}
      <section className="rounded-xl bg-white/[0.03] p-6" aria-label="Merchant profile">
        <p className="label-sm text-faint">Merchant Profile</p>
        <div className="mt-5 flex items-center gap-4">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-ai font-display text-lg font-semibold text-background">
            {(profile?.businessName ?? session?.businessName ?? "?").charAt(0).toUpperCase()}
          </span>
          <dl className="grid flex-1 gap-x-8 gap-y-3 text-[0.8125rem] sm:grid-cols-2">
            <div>
              <dt className="label-sm text-faint">Business</dt>
              <dd className="mt-0.5 text-foreground">{profile?.businessName ?? session?.businessName ?? "—"}</dd>
            </div>
            <div>
              <dt className="label-sm text-faint">Work Email</dt>
              <dd className="num mt-0.5 text-foreground">{profile?.email ?? session?.email ?? "—"}</dd>
            </div>
            <div>
              <dt className="label-sm text-faint">Currency</dt>
              <dd className="num mt-0.5 text-foreground">INR (₹)</dd>
            </div>
            <div>
              <dt className="label-sm text-faint">Environment</dt>
              <dd className="mt-0.5 text-foreground">{profile?.environment === "LIVE" ? "Production" : "Test Mode (Razorpay Sandbox)"}</dd>
            </div>
          </dl>
        </div>
      </section>

      {/* integration configuration */}
      <section className="rounded-xl bg-white/[0.03] p-6" aria-label="Integration configuration">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="label-sm inline-flex items-center gap-2 text-muted-foreground">
              <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
              Razorpay Test Mode Integration
            </p>
            <p className="mt-2 max-w-xl text-[0.8125rem] text-muted-foreground">
              Connect your Razorpay Test Mode account to enable payment recovery operations.
              Credentials are encrypted at rest and never exposed to the frontend after submission.
            </p>
          </div>
          <span className={cn("chip shrink-0", razorpayConnected ? "chip-success" : "chip-warning")}>
            {razorpayConnected ? (
              <>
                <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                Connected
              </>
            ) : (
              <>
                <WifiOff className="h-3 w-3" aria-hidden="true" />
                Not Connected
              </>
            )}
          </span>
        </div>

        {!razorpayConnected ? (
          // Show input form when not connected
          <div className="mt-5 grid gap-5 sm:grid-cols-2 animate-in fade-in slide-in-from-top-2 duration-300 ease-out">
            <label className="block">
              <span className="label-sm text-faint">Razorpay Key ID</span>
              <input
                type="text"
                placeholder="rzp_test_xxxxxxxxxxxx"
                autoComplete="off"
                maxLength={100}
                value={keyId}
                onChange={(e) => setKeyId(e.target.value)}
                className="input-field num mt-2 w-full transition-all duration-200 hover:border-border/50 focus:ring-2 focus:ring-foreground/30 focus:border-foreground"
              />
            </label>
            <label className="block">
              <span className="label-sm text-faint">Razorpay Key Secret</span>
              <input
                type="password"
                placeholder="••••••••••••••••"
                autoComplete="off"
                maxLength={100}
                value={keySecret}
                onChange={(e) => setKeySecret(e.target.value)}
                className="input-field num mt-2 w-full transition-all duration-200 hover:border-border/50 focus:ring-2 focus:ring-foreground/30 focus:border-foreground"
              />
            </label>
          </div>
        ) : (
          // Show connected status with masked key ID
          <div className="mt-5 grid gap-5 sm:grid-cols-2 animate-in fade-in slide-in-from-top-2 duration-300 ease-out">
            <div className="block">
              <span className="label-sm text-faint">Razorpay Key ID</span>
              <div className="num mt-2 w-full rounded-lg border border-border bg-surface-low px-3 py-2.5 text-[0.8125rem] text-foreground">
                {keyId ? `rzp_test_${"*".repeat(Math.max(0, keyId.length - 10))}${keyId.slice(-4)}` : "Connected"}
              </div>
            </div>
            <div className="block">
              <span className="label-sm text-faint">Razorpay Key Secret</span>
              <div className="num mt-2 w-full rounded-lg border border-border bg-surface-low px-3 py-2.5 text-[0.8125rem] text-foreground">
                ••••••••••••••••
              </div>
            </div>
          </div>
        )}

        <div className="mt-5 flex flex-wrap gap-3">
          {!razorpayConnected && (
            <button
              className="btn-primary"
              onClick={handleSaveCredentials}
              disabled={savingCredentials || !keyId || !keySecret}
              aria-busy={savingCredentials}
            >
              {savingCredentials ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Saving…
                </>
              ) : (
                <>
                  <KeyRound className="h-4 w-4 mr-2" aria-hidden="true" />
                  Save Credentials
                </>
              )}
            </button>
          )}
          {razorpayConnected && (
            <button
              className="btn-primary"
              onClick={handleTestConnection}
              disabled={testingConnection}
              aria-busy={testingConnection}
            >
              {testingConnection ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Testing…
                </>
              ) : (
                <>
                  <Wifi className="h-4 w-4 mr-2" aria-hidden="true" />
                  Test Connection
                </>
              )}
            </button>
          )}
        </div>

        {saveError && (
          <p className="mt-3 text-[0.8125rem] text-error animate-in fade-in slide-in-from-top-2 duration-200 ease-out" role="alert">
            <XCircle className="h-4 w-4 inline mr-1" aria-hidden="true" />
            {saveError}
          </p>
        )}

        {testResult && (
          <p className={cn("mt-3 text-[0.8125rem] animate-in fade-in slide-in-from-top-2 duration-200 ease-out", testResult.success ? "text-success" : "text-error")} role="status">
            {testResult.success ? (
              <>
                <CheckCircle2 className="h-4 w-4 inline mr-1" aria-hidden="true" />
                {testResult.message}
              </>
            ) : (
              <>
                <XCircle className="h-4 w-4 inline mr-1" aria-hidden="true" />
                {testResult.message}
              </>
            )}
          </p>
        )}

        {/* Webhook Status */}
        {webhookStatus !== null && (
          <div className="mt-5 p-4 rounded-xl border border-border bg-surface-low">
            <p className="label-sm text-faint">Webhook Status</p>
            <div className="mt-2 flex items-center gap-3">
              <span className={cn("chip", webhookStatus.configured ? "chip-success" : "chip-warning")}>
                {webhookStatus.configured ? (
                  <>
                    <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                    Configured
                  </>
                ) : (
                  <>
                    <XCircle className="h-3 w-3" aria-hidden="true" />
                    Not Configured
                  </>
                )}
              </span>
              {webhookStatus.lastVerified && (
                <span className="text-[0.75rem] text-muted-foreground">
                  Last verified: {new Date(webhookStatus.lastVerified).toLocaleString()}
                </span>
              )}
              <button
                className="btn-ghost !py-1 text-[0.75rem] ml-auto"
                onClick={() => {
                  fetchWebhookStatus();
                  toast.info("Refreshing webhook status…");
                }}
                disabled={testingConnection}
              >
                <RotateCcw className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
                Refresh
              </button>
            </div>
            {!webhookStatus.configured && (
              <p className="mt-3 text-[0.75rem] text-muted-foreground">
                To configure webhooks, add your webhook secret in the Razorpay Dashboard and ensure it matches
                the secret configured in your RecoverAI environment. The webhook URL should point to
                <code className="px-1.5 py-0.5 rounded bg-surface-low font-mono text-[0.75rem] text-foreground">/api/webhooks/razorpay</code>.
              </p>
            )}
          </div>
        )}

        <p className="mt-4 inline-flex items-start gap-1.5 text-[0.75rem] text-faint">
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden="true" />
          Test Mode only — never enter live credentials. Secrets are encrypted at rest and never returned by the API.
        </p>
      </section>

      {/* notification preferences */}
      <section className="rounded-xl bg-white/[0.03] p-6" aria-label="Notification preferences">
        <p className="label-sm text-faint">Notification Preferences</p>
        <div className="mt-5 space-y-1">
          {NOTIFICATION_PREFS.map((n) => (
            <div
              key={n.key}
              className="flex items-center justify-between gap-4 border-b border-border py-3 text-[0.8125rem] last:border-0 last:pb-0"
            >
              <span>
                <span className="text-foreground">{n.label}</span>
                <span className="mt-0.5 block text-[0.75rem] text-muted-foreground">{n.copy}</span>
              </span>
              <Toggle
                checked={prefs[n.key]}
                onChange={(checked) => setPrefs((prev) => ({ ...prev, [n.key]: checked }))}
                label={n.label}
              />
            </div>
          ))}
        </div>
      </section>

      {/* account */}
      <section className="rounded-xl bg-white/[0.03] p-6" aria-label="Account">
        <p className="label-sm text-faint">Account</p>
        <p className="mt-3 max-w-xl text-[0.8125rem] text-muted-foreground">
          Signing out clears your session from this browser. You can sign back in
          with your email and password at any time.
        </p>
        <button
          className="btn-ghost mt-5 !py-2"
          onClick={() => {
            signOut();
            navigate({ to: "/" });
          }}
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Sign out
        </button>
      </section>
    </div>
  );
}
