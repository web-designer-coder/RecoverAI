import { clearSession } from "./auth";
import type {
  DashboardData,
  RecoveryPayment,
  RecoveryPaymentDetail,
  AuditEvent,
  PolicyRules,
  SimulationInput,
  SimulationResult,
  RecoveryFilters,
  ExecuteResult,
  PolicyCheck,
  PolicyCheckKind,
  AnalyzeResponse,
  PolicyValidationResponse,
  ExecutionResponse,
  DashboardResponse,
  RecoveryPaymentResponse,
  RecoveryPaymentDetailResponse,
  AuditEventResponse,
  AnalyticsResponse,
  SimulationResponse,
  PolicyResponse,
  PolicyUpsertRequest,
  SimulationCreateRequest,
  AnalyticsData,
  RecommendedAction,
  FailureCategory,
  RecoveryStatus,
  Priority,
  PaymentMethod,
  AuditEventType,
  AuditCategory
} from "./types";

// Re-export types that components may import directly
export type { PolicyCheck, PolicyCheckKind };

const API_BASE_URL = import.meta.env['VITE_API_BASE_URL'] || '/api';

function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem('recoverai.session');
    if (!raw) return null;
    const session = JSON.parse(raw);
    return session?.token || null;
  } catch {
    return null;
  }
}

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };
  const token = getAuthToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Set up timeout controller
  const timeout = options.timeout as number | undefined;
  const controller = new AbortController();
  const timeoutId = timeout && setTimeout(() => controller.abort(), timeout);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    // Clear timeout on error
    if (timeoutId) clearTimeout(timeoutId);
    // Network failure — fetch throws TypeError on DNS/CORS/offline
    if (err instanceof TypeError && String(err.message).includes('Failed to fetch')) {
      throw new ApiError('NETWORK_ERROR', 'Network error — please check your connection and try again', 0);
    }
    if (err.name === 'AbortError') {
      throw new ApiError('TIMEOUT_ERROR', 'Request timed out — please check your connection and try again', 0);
    }
    throw new ApiError('NETWORK_ERROR', 'Unable to reach the server', 0);
  } finally {
    // Clear timeout if request completed
    if (timeoutId) clearTimeout(timeoutId);
  }

  if (!response.ok) {
    // On 401: clear stale/expired session and redirect to login.
    // Skip unauthenticated endpoints (signup, signin) that legitimately return 401.
    const isUnauthMerchantEndpoint = /^\/merchants(?!\/me)/.test(endpoint);
    if (response.status === 401 && !isUnauthMerchantEndpoint) {
      clearSession();
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
    }
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(
      errorData?.error?.code || 'UNKNOWN_ERROR',
      errorData?.error?.message || 'An unknown error occurred',
      response.status
    );
  }

  // Handle non-JSON responses gracefully
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    // 204 No Content or empty body
    if (response.status === 204) {
      return undefined as T;
    }
    const text = await response.text().catch(() => '');
    if (!text) {
      return undefined as T;
    }
    throw new ApiError('UNEXPECTED_RESPONSE', 'Server returned a non-JSON response', response.status);
  }

  return response.json();
}

// Transform helper functions

// Current policies store (for synchronous policy evaluation)
let currentPolicies: PolicyRules | null = null;
function toCamelCase(obj: any): any {
  if (Array.isArray(obj)) {
    return obj.map(toCamelCase);
  }
  if (obj !== null && typeof obj === 'object') {
    return Object.keys(obj).reduce((acc, key) => {
      const camelKey = key.replace(/_([a-z])/g, (_, char) => char.toUpperCase());
      acc[camelKey] = toCamelCase(obj[key]);
      return acc;
    }, {} as any);
  }
  return obj;
}
function toSnakeCase(obj: any): any {
  if (Array.isArray(obj)) {
    return obj.map(toSnakeCase);
  }
  if (obj !== null && typeof obj === 'object') {
    return Object.keys(obj).reduce((acc, key) => {
      const snakeKey = key.replace(/[A-Z]/g, (char) => `_${char.toLowerCase()}`);
      acc[snakeKey] = toSnakeCase(obj[key]);
      return acc;
    }, {} as any);
  }
  return obj;
}

class ApiError extends Error {
  public code: string;
  public status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
    this.name = 'ApiError';
  }
}

// API service functions
export const api = {
  // Dashboard
  getDashboard: async (): Promise<DashboardData> => {
    const data = await apiFetch<DashboardResponse>('/dashboard');
    return transformDashboardData(data);
  },

  // Recoveries
  getRecoveries: async (filters: RecoveryFilters = {}): Promise<RecoveryPayment[]> => {
    const params = new URLSearchParams();
    if (filters.status && filters.status !== 'ALL') params.append('status', filters.status);
    if (filters.category) params.append('category', filters.category);
    if (filters.search) params.append('search', filters.search);

    const data = await apiFetch<RecoveryPaymentResponse[]>(`/recoveries?${params}`);
    return data.map(transformRecoveryPayment);
  },

  getRecovery: async (id: string): Promise<RecoveryPaymentDetail | null> => {
    try {
      const data = await apiFetch<RecoveryPaymentDetailResponse>(`/recoveries/${id}`);
      return transformRecoveryPaymentDetail(data);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return null;
      }
      throw error;
    }
  },

  getRecoveryAudit: async (paymentId: string): Promise<AuditEvent[]> => {
    const data = await apiFetch<AuditEventResponse[]>(`/recoveries/${paymentId}/audit`);
    return data.map(transformAuditEvent);
  },

  // Analysis
  analyzeRecovery: async (id: string): Promise<RecoveryPaymentDetail | null> => {
    try {
      const data = await apiFetch<AnalyzeResponse>(`/recoveries/${id}/analyze`, { method: 'POST' });
      // The analyze endpoint returns analysis results, we need to get the updated recovery detail
      const updatedRecovery = await apiFetch<RecoveryPaymentDetailResponse>(`/recoveries/${id}`);
      return transformRecoveryPaymentDetail(updatedRecovery);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return null;
      }
      throw error;
    }
  },

  // Policy validation
  validatePolicy: async (paymentId: string): Promise<PolicyValidationResponse> => {
    return await apiFetch<PolicyValidationResponse>(`/recoveries/${paymentId}/validate-policy`, { method: 'POST' });
  },

  // Execution
  executeRecovery: async (paymentId: string): Promise<ExecuteResult | null> => {
    try {
      const data = await apiFetch<ExecutionResponse>(`/recoveries/${paymentId}/execute`, { method: 'POST' });
      const payment = await apiFetch<RecoveryPaymentDetailResponse>(`/recoveries/${paymentId}`);

      // Transform policy checks from execution response to frontend format
      const policyChecks: PolicyCheck[] = data.checks.map(check => ({
        label: check.check_name,
        detail: check.message,
        passed: check.status === 'PASS',
        kind: check.severity as PolicyCheckKind // Assuming severity maps to kind
      }));

      return {
        payment: transformRecoveryPaymentDetail(payment),
        policyChecks
      };
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return null;
      }
      throw error;
    }
  },

  stopRecovery: async (id: string): Promise<RecoveryPaymentDetail | null> => {
    try {
      const data = await apiFetch<RecoveryPaymentResponse>(`/recoveries/${id}/stop`, { method: 'POST' });
      const payment = transformRecoveryPayment(data);
      // Convert to RecoveryPaymentDetail by adding decision, actions, and customer fields
      return {
        ...payment,
        decision: null,
        actions: [],
        customer_name: null,
        customer_email: null,
        customer_phone: null,
        provider_order_id: null,
        provider_status: null,
      };
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return null;
      }
      throw error;
    }
  },

  // Analytics
  getAnalytics: async (): Promise<AnalyticsData> => {
    const data = await apiFetch<AnalyticsResponse>('/analytics');
    return transformAnalyticsData(data);
  },

  // Audit
  getAudit: async (category?: string): Promise<AuditEvent[]> => {
    const params = new URLSearchParams();
    if (category && category !== 'ALL') {
      params.append('category', category);
    }

    const data = await apiFetch<AuditEventResponse[]>(`/audit?${params}`);
    return data.map(transformAuditEvent);
  },

  // Simulation
  runSimulation: async (input: SimulationInput): Promise<SimulationResult> => {
    const backendInput: SimulationCreateRequest = {
      transactions: input.transactions,
      average_amount: input.avgTransactionAmount,
      failure_rate: input.failureRate,
      recovery_window_days: input.recoveryWindowDays
    };

    const data = await apiFetch<SimulationResponse>('/simulations', {
      method: 'POST',
      body: JSON.stringify(backendInput)
    });

    return transformSimulationResult(data, input);
  },

  getSimulations: async (): Promise<SimulationResponse[]> => {
    const data = await apiFetch<SimulationResponse[]>('/simulations');
    return data;
  },

  getSimulation: async (id: string): Promise<SimulationResponse | null> => {
    try {
      const data = await apiFetch<SimulationResponse>(`/simulations/${id}`);
      return data;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        return null;
      }
      throw error;
    }
  },

  // Policies
  getPolicies: async (): Promise<PolicyRules> => {
    const data = await apiFetch<PolicyResponse>('/policies');
    const policies = transformPolicyResponse(data);
    currentPolicies = policies;
    return policies;
  },

  updatePolicies: async (policies: PolicyRules): Promise<PolicyRules> => {
    const backendPolicies: PolicyUpsertRequest = {
      maximum_retries: policies.maxRetries,
      recovery_window_days: policies.recoveryWindowDays,
      minimum_ai_confidence: policies.minConfidence,
      high_value_threshold: policies.highValueThreshold,
      prevent_duplicate_recovery: policies.preventDuplicates,
      require_policy_approval: policies.requirePolicyApproval,
      maintain_audit_log: policies.maintainAuditLog,
      escalate_high_value: policies.escalateHighValue,
      failure_rules: transformFailureRulesToBackend(policies.failureRules)
    };

    const data = await apiFetch<PolicyResponse>('/policies', {
      method: 'PUT',
      body: JSON.stringify(backendPolicies)
    });

    const updatedPolicies = transformPolicyResponse(data);
    currentPolicies = updatedPolicies;
    return updatedPolicies;
  },

  // Merchants (single authoritative block — Phase 9.1 clean)
  signUp: async (businessName: string, email: string, password: string): Promise<Session> => {
    const data = await apiFetch<MerchantResponse>('/merchants', {
      method: 'POST',
      body: JSON.stringify({ businessName, email, password })
    });
    return {
      email: data.email,
      businessName: data.businessName,
      merchantId: data.id,
      ...(data.token ? { token: data.token } : {}),
    };
  },

  signIn: async (email: string, password: string): Promise<Session> => {
    const data = await apiFetch<MerchantResponse>('/merchants/signin', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    return {
      email: data.email,
      businessName: data.businessName,
      merchantId: data.id,
      ...(data.token ? { token: data.token } : {}),
    };
  },

  getMerchantProfile: async (): Promise<MerchantProfile> => {
    return await apiFetch<MerchantProfile>('/merchants/me');
  },

  updateMerchantRazorpayCredentials: async (keyId: string, keySecret: string): Promise<void> => {
    await apiFetch<MessageResponse>('/merchants/me/razorpay', {
      method: 'POST',
      body: JSON.stringify({ keyId, keySecret })
    });
  },

  testRazorpayConnection: async (): Promise<{ status: string; message: string }> => {
    return await apiFetch<{ status: string; message: string }>('/merchants/me/razorpay/test');
  },

  getRazorpayIntegration: async (): Promise<{ configured: boolean; keyId: string | null; keySecretSet: boolean }> => {
    return await apiFetch<{ configured: boolean; keyId: string | null; keySecretSet: boolean }>('/merchants/me/razorpay');
  },

  getRazorpayWebhookStatus: async (): Promise<{ configured: boolean; lastVerified: string | null }> => {
    return await apiFetch<{ configured: boolean; lastVerified: string | null }>('/merchants/me/razorpay/webhook-status');
  },

  getMerchantPolicies: async (): Promise<PolicyRules> => {
    const data = await apiFetch<PolicyResponse>('/merchants/me/policies');
    return transformPolicyResponse(data);
  },

  updateMerchantPolicies: async (policies: PolicyRules): Promise<PolicyRules> => {
    const data = await apiFetch<PolicyResponse>('/merchants/me/policies', {
      method: 'PUT',
      body: JSON.stringify(policies)
    });
    return transformPolicyResponse(data);
  },
};

// Individual named exports for backward compatibility
export const getDashboard = api.getDashboard;
export const getRecoveries = api.getRecoveries;
export const getRecovery = api.getRecovery;
export const getRecoveryAudit = api.getRecoveryAudit;
export const analyzeRecovery = api.analyzeRecovery;
export const validatePolicy = api.validatePolicy;
export const executeRecovery = api.executeRecovery;
export const stopRecovery = api.stopRecovery;
export const getAnalytics = api.getAnalytics;
export const getAudit = api.getAudit;
export const runSimulation = api.runSimulation;
export const getSimulations = api.getSimulations;
export const getSimulation = api.getSimulation;
export const getPolicies = api.getPolicies;
export const updatePolicies = api.updatePolicies;
export const signIn = api.signIn;
export const signUp = api.signUp;
export const getMerchantProfile = api.getMerchantProfile;
export const updateMerchantRazorpayCredentials = api.updateMerchantRazorpayCredentials;
export const testRazorpayConnection = api.testRazorpayConnection;
export const getRazorpayWebhookStatus = api.getRazorpayWebhookStatus;
export const getRazorpayIntegration = api.getRazorpayIntegration;
export const getMerchantPolicies = api.getMerchantPolicies;
export const updateMerchantPolicies = api.updateMerchantPolicies;

// Lightweight polling for data freshness. Consumers already call the fetch
// function once on mount; this re-invokes it at a fixed interval so the UI
// stays reasonably current without WebSockets.
const POLL_INTERVAL_MS = 30_000;

export function subscribeStore(callback: () => void): () => void {
  const id = setInterval(callback, POLL_INTERVAL_MS);
  return () => clearInterval(id);
}

// Evaluate policy checks for a payment or decision
export function evaluatePolicyChecks(paymentOrDecision: RecoveryPayment | {
  recommended_action: RecommendedAction | null;
  failure_category: FailureCategory;
}): PolicyCheck[] {
  // If no policies are loaded, return empty array
  if (!currentPolicies) {
    return [];
  }

  // Extract the recommended action and failure category
  let recommendedAction: RecommendedAction | null = null;
  let failureCategory: FailureCategory = 'OTHER'; // default

  if ('recommended_action' in paymentOrDecision && 'failure_category' in paymentOrDecision) {
    // This is a decision object
    recommendedAction = paymentOrDecision.recommended_action;
    failureCategory = paymentOrDecision.failure_category;
  } else if ('recommended_action' in paymentOrDecision) {
    // This is a full payment object
    recommendedAction = (paymentOrDecision as RecoveryPayment).recommended_action;
    failureCategory = (paymentOrDecision as RecoveryPayment).failure_category;
  }

  // If no recommended action, return empty checks
  if (!recommendedAction) {
    return [];
  }

  // Get the policy for this failure category
  // Note: The following line is safe because failureRules is recorded with all FailureCategory keys
  const policyAction = currentPolicies.failureRules[failureCategory];

  // Check if the recommended action matches the policy
  const passed = recommendedAction === policyAction;

  // Determine the kind based on policy action
  let kind: PolicyCheckKind = 'fail';
  if (passed) {
    kind = 'pass';
  } else if (policyAction === 'ESCALATE') {
    kind = 'escalate';
  }

  // Create descriptive labels
  const actionLabels: Record<RecommendedAction, string> = {
    RETRY: 'Retry Payment',
    PAYMENT_UPDATE: 'Update Payment Details',
    NOTIFY: 'Notify Customer',
    STOP: 'Stop Recovery',
    ESCALATE: 'Escalate to Operator'
  };

  const failureLabels: Record<FailureCategory, string> = {
    INSUFFICIENT_FUNDS: 'Insufficient Funds',
    EXPIRED_CARD: 'Expired Card',
    NETWORK_FAILURE: 'Network Failure',
    BANK_DECLINE: 'Bank Decline',
    INVALID_DETAILS: 'Invalid Details',
    OTHER: 'Other Failure Reason'
  };

  return [{
    label: `Policy Check: ${actionLabels[recommendedAction]}`,
    detail: `${failureLabels[failureCategory]} failures should be handled with ${actionLabels[policyAction || 'ESCALATE']} per policy`,
    passed,
    kind
  }];
}

// TRANSFORMATION FUNCTIONS

function transformDashboardData(backend: DashboardResponse): DashboardData {
  return {
    kpis: {
      revenueAtRisk: backend.kpis.revenue_at_risk,
      recoveredRevenue: backend.kpis.recovered_revenue,
      recoveryRate: backend.kpis.recovery_rate,
      incrementalRevenue: backend.kpis.incremental_revenue,
      activeRecoveries: backend.kpis.active_recoveries,
      paymentsAtRisk: backend.kpis.payments_at_risk
    },
    funnel: backend.funnel.map(step => ({
      label: step.label,
      value: step.value,
      isCurrency: step.is_currency
    })),
    aiVsStatic: backend.ai_vs_static.map(row => ({
      metric: row.metric,
      static: row.static,
      ai: row.ai,
      delta: row.delta
    })),
    failureBreakdown: backend.failure_breakdown.map(item => ({
      category: item.category as FailureCategory,
      label: item.label,
      count: item.count,
      amount: item.amount
    })),
    recoveredSeries: backend.recovered_series.map(point => ({
      month: point.month,
      recovered: point.recovered,
      baseline: point.baseline
    }))
  };
}

function transformRecoveryPayment(backend: RecoveryPaymentResponse): RecoveryPayment {
  return {
    payment_id: backend.payment_id,
    customer_id: backend.customer_id,
    amount: backend.amount,
    currency: backend.currency as 'INR',
    failure_reason: backend.failure_reason,
    failure_category: backend.failure_category as FailureCategory,
    retry_count: backend.retry_count,
    recovery_probability: backend.recovery_probability,
    confidence: backend.confidence,
    recommended_action: backend.recommended_action as RecommendedAction,
    recommended_at: backend.recommended_at ?? '',
    expected_recovery: backend.expected_recovery,
    status: backend.status as RecoveryStatus,
    priority: backend.priority as Priority,
    payment_method: backend.payment_method as PaymentMethod,
    created_at: backend.created_at,
    failed_at: backend.failed_at,
    next_action_at: backend.next_action_at ?? null
  };
}

function transformRecoveryPaymentDetail(backend: RecoveryPaymentDetailResponse): RecoveryPaymentDetail {
  const base = transformRecoveryPayment(backend);

  return {
    ...base,
    decision: backend.decision ? {
      diagnosis: backend.decision.diagnosis ?? null,
      confidence: backend.decision.confidence ?? 0,
      recovery_probability: backend.decision.recovery_probability ?? 0,
      recommended_action: backend.decision.recommended_action as RecommendedAction | null,
      expected_recovery: backend.decision.expected_recovery ?? 0,
      optimal_recovery_at: backend.decision.optimal_recovery_at ?? null,
      model_version: backend.decision.model_version ?? null,
      signals: backend.decision.signals || [],
      explanation: backend.decision.explanation ?? null,
      data_sufficiency: backend.decision.data_sufficiency ?? null,
      optimal_window: backend.decision.optimal_window ?? null,
    } : null,
    actions: backend.actions.map(action => ({
      id: action.id,
      action_type: action.action_type,
      status: action.status,
      scheduled_at: action.scheduled_at ?? null,
      started_at: action.started_at ?? null,
      completed_at: action.completed_at ?? null,
      external_reference: action.external_reference ?? null
    })),
    customer_name: backend.customer?.name ?? null,
    customer_email: backend.customer?.email ?? null,
    customer_phone: backend.customer?.phone ?? null,
    provider_order_id: backend.provider_order_id ?? null,
    provider_status: backend.provider_status ?? null,
  };
}

function transformAuditEvent(backend: AuditEventResponse): AuditEvent {
  // Backend sends `metadata`, but some legacy rows may have `detail`.
  // We map both into a single string-keyed record so the UI can render
  // either shape without crashing.
  const rawMeta = backend.metadata ?? (backend as unknown as { detail?: Record<string, string> }).detail ?? {};

  // Defensive: ensure all values are strings (backend may send nested objects/arrays).
  const safeMeta: Record<string, string> = {};
  for (const [k, v] of Object.entries(rawMeta)) {
    if (v == null) continue;
    if (typeof v === "string") {
      safeMeta[k] = v;
    } else if (typeof v === "number" || typeof v === "boolean") {
      safeMeta[k] = String(v);
    } else if (Array.isArray(v)) {
      safeMeta[k] = v.map((x) => (x == null ? "" : typeof x === "string" ? x : JSON.stringify(x))).join(", ");
    } else {
      try {
        safeMeta[k] = JSON.stringify(v);
      } catch {
        safeMeta[k] = "[object]";
      }
    }
  }

  const auditEvent: AuditEvent = {
    id: backend.id,
    timestamp: backend.timestamp,
    type: backend.event_type as AuditEventType,
    category: backend.category as AuditCategory,
    payment_id: backend.payment_id ?? '',
    summary: backend.summary,
    detail: safeMeta
  };
  if (backend.amount !== null && backend.amount !== undefined) {
    auditEvent.amount = backend.amount;
  }
  return auditEvent;
}

function transformAnalyticsData(backend: AnalyticsResponse): AnalyticsData {
  return {
    performance: backend.performance.map(point => {
      // Defensive: ensure month is valid YYYY-MM format for chart date parsing
      const month = (point.month && /^\d{4}-\d{2}$/.test(point.month))
        ? point.month
        : new Date().toISOString().slice(0, 7); // fallback to current month
      return { month, ai: point.ai_rate, static: point.static_rate };
    }),
    byCategory: backend.by_category.map(item => ({
      label: item.label,
      recovered: item.recovered,
      rate: item.rate
    })),
    byMethod: backend.by_method.map(item => ({
      label: item.label,
      recovered: item.recovered,
      rate: item.rate,
      share: item.share
    })),
    byAttempt: backend.by_attempt.map(item => ({
      attempt: item.attempt,
      rate: item.rate,
      recovered: item.recovered
    })),
    avgTimeToRecoveryHours: {
      static: backend.avg_time_to_recovery_hours.static_hours,
      ai: backend.avg_time_to_recovery_hours.ai_hours
    }
  };
}

function transformSimulationResult(backend: SimulationResponse, input: SimulationInput): SimulationResult {
  const failedPayments = Math.round(input.transactions * input.failureRate);
  const revenueAtRisk = failedPayments * input.avgTransactionAmount;

  // Use backend-computed recovery values directly (they use real analytics data)
  const aiRecovered = Math.round(backend.ai_recovered_revenue);
  const staticRecovered = Math.round(backend.static_recovered_revenue);
  const incrementalRevenue = Math.round(backend.incremental_revenue);

  // Distribute action counts across the failed population.
  // Shares reflect typical recovery queue composition: most failures are retryable,
  // some need payment detail updates, a few need customer outreach, the rest are
  // escalated or halted by policy.
  const retryCount = Math.round(failedPayments * 0.58);
  const updateCount = Math.round(failedPayments * 0.19);
  const notifyCount = Math.round(failedPayments * 0.11);
  const escalateCount = Math.round(failedPayments * 0.07);
  const stoppedCount = failedPayments - retryCount - updateCount - notifyCount - escalateCount;

  // Recovered revenue is distributed by action effectiveness:
  // Retries recover the most, payment updates less, notifications minimal.
  // Escalations and stops produce no direct recovery.
  const retryRecovered = Math.round(aiRecovered * 0.65);
  const updateRecovered = Math.round(aiRecovered * 0.25);
  const notifyRecovered = aiRecovered - retryRecovered - updateRecovered;

  const actionBreakdown: { action: string; count: number; recovered: number }[] = [
    { action: 'Retry', count: retryCount, recovered: retryRecovered },
    { action: 'Payment Update', count: updateCount, recovered: updateRecovered },
    { action: 'Customer Notification', count: notifyCount, recovered: notifyRecovered },
    { action: 'Escalation', count: escalateCount, recovered: 0 },
    { action: 'Stopped', count: Math.max(0, stoppedCount), recovered: 0 }
  ];

  return {
    id: backend.id,
    input,
    transactionsAnalyzed: backend.transactions,
    failedPayments,
    revenueAtRisk,
    staticRecovered,
    staticRate: backend.static_recovery_rate,
    aiRecovered,
    aiRate: backend.ai_recovery_rate,
    incrementalRevenue,
    actionBreakdown,
    policyViolations: escalateCount,
    createdAt: backend.created_at
  };
}

function transformPolicyResponse(backend: PolicyResponse): PolicyRules {
  // Map all FailureCategory to a default (ESCALATE) then override with backend values
  const frontendFailureRules: Record<FailureCategory, RecommendedAction> = {
    INSUFFICIENT_FUNDS: 'ESCALATE',
    EXPIRED_CARD: 'ESCALATE',
    NETWORK_FAILURE: 'ESCALATE',
    BANK_DECLINE: 'ESCALATE',
    INVALID_DETAILS: 'ESCALATE',
    OTHER: 'ESCALATE'
  };

  // Mapping from canonical actions to frontend aliases
  const canonicalToFrontend: Record<string, RecommendedAction> = {
    'RETRY': 'RETRY',
    'PAYMENT_UPDATE': 'PAYMENT_UPDATE',
    'CUSTOMER_NOTIFICATION': 'NOTIFY',
    'STOP': 'STOP',
    'ESCALATE': 'ESCALATE'
  };

  for (const [category, canonicalAction] of Object.entries(backend.failure_rules)) {
    const frontendAction = canonicalToFrontend[canonicalAction];
    if (frontendAction !== undefined) {
      frontendFailureRules[category as FailureCategory] = frontendAction;
    }
    // If canonicalAction not recognized, keep default ESCALATE
  }

  return {
    maxRetries: backend.maximum_retries,
    recoveryWindowDays: backend.recovery_window_days,
    minConfidence: backend.minimum_ai_confidence,
    highValueThreshold: backend.high_value_threshold,
    failureRules: frontendFailureRules,
    preventDuplicates: backend.prevent_duplicate_recovery,
    requirePolicyApproval: backend.require_policy_approval,
    maintainAuditLog: backend.maintain_audit_log,
    escalateHighValue: backend.escalate_high_value
  };
}

function transformFailureRulesToBackend(frontendRules: Record<FailureCategory, RecommendedAction>): Record<string, string> {
  // Mapping from frontend aliases to canonical actions
  const frontendToCanonical: Record<RecommendedAction, string> = {
    'RETRY': 'RETRY',
    'PAYMENT_UPDATE': 'PAYMENT_UPDATE',
    'NOTIFY': 'CUSTOMER_NOTIFICATION',
    'STOP': 'STOP',
    'ESCALATE': 'ESCALATE'
  };

  const backendRules: Record<string, string> = {};
  for (const [category, frontendAction] of Object.entries(frontendRules)) {
    backendRules[category] = frontendToCanonical[frontendAction];
  }

  return backendRules;
}

// Additional types for the new merchant API
export interface Session {
  email: string;
  businessName: string;
  merchantId: string;
  token?: string;
}

export interface MerchantProfile {
  id: string;
  businessName: string;
  email: string;
  status: string;
  environment: string;
  razorpayConfigured?: boolean;
  webhookConfigured?: boolean;
}

export interface MerchantResponse {
  id: string;
  businessName: string;
  email: string;
  status: string;
  environment: string;
  token?: string;
}

export interface Merchant {
  id: string;
  businessName: string;
  email: string;
  status: string;
  environment: string;
}

export interface MessageResponse {
  message: string;
}

export interface ConnectionTestResponse {
  status: string;
  message: string;
}

export interface WebhookStatusResponse {
  configured: boolean;
  lastVerified: string | null;
}