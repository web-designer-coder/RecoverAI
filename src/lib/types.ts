// RecoverAI domain types shared across the API layer and the UI.

export type FailureCategory =
  | "INSUFFICIENT_FUNDS"
  | "EXPIRED_CARD"
  | "NETWORK_FAILURE"
  | "BANK_DECLINE"
  | "INVALID_DETAILS"
  | "OTHER";

export type RecommendedAction =
  | "RETRY"
  | "PAYMENT_UPDATE"
  | "NOTIFY"
  | "STOP"
  | "ESCALATE";

export type RecoveryStatus =
  | "QUEUED"
  | "SCHEDULED"
  | "PROCESSING"
  | "RECOVERED"
  | "HALTED"
  | "NEEDS_ACTION";

export type Priority = "HIGH" | "MEDIUM" | "LOW";

export type PaymentMethod = "UPI" | "CARD" | "NET_BANKING";

export interface RecoveryPayment {
  payment_id: string;
  customer_id: string;
  amount: number;
  currency: "INR";
  failure_reason: string;
  failure_category: FailureCategory;
  retry_count: number;
  recovery_probability: number;
  confidence: number;
  recommended_action: RecommendedAction;
  recommended_at: string;
  expected_recovery: number;
  status: RecoveryStatus;
  priority: Priority;
  payment_method: PaymentMethod;
  created_at: string;
  failed_at: string;
  next_action_at: string | null;
}

// Extended recovery payment with decision and actions for detail view
export interface RecoveryPaymentDetail extends RecoveryPayment {
  decision: {
    diagnosis: string | null;
    confidence: number;
    recovery_probability: number;
    recommended_action: RecommendedAction | null;
    expected_recovery: number;
    optimal_recovery_at: string | null;
    model_version: string | null;
    signals: { name: string; value: string; impact: string; category: string }[];
    explanation: string | null;
    data_sufficiency: string | null;
    optimal_window: string | null;
  } | null;
  actions: {
    id: string;
    action_type: string;
    status: string;
    scheduled_at: string | null;
    started_at: string | null;
    completed_at: string | null;
    external_reference: string | null;
  }[];
  customer_name: string | null;
  customer_email: string | null;
  customer_phone: string | null;
  provider_order_id: string | null;
  provider_status: string | null;
}

export type AuditEventType =
  | "PAYMENT_FAILED"
  | "AI_DIAGNOSIS"
  | "RECOVERY_PREDICTION"
  | "ACTION_SELECTED"
  | "POLICY_CHECK"
  | "RECOVERY_SCHEDULED"
  | "RECOVERY_EXECUTED"
  | "PAYMENT_RECOVERED"
  | "RECOVERY_HALTED"
  | "CUSTOMER_NOTIFIED";

export type AuditCategory = "AI_DECISION" | "POLICY" | "EXECUTION" | "RESULT";

export interface AuditEvent {
  id: string;
  timestamp: string;
  type: AuditEventType;
  category: AuditCategory;
  payment_id: string;
  summary: string;
  amount?: number;
  detail: Record<string, string>;
}

export interface PolicyRules {
  maxRetries: number;
  recoveryWindowDays: number;
  minConfidence: number;
  highValueThreshold: number;
  failureRules: Record<FailureCategory, RecommendedAction>;
  preventDuplicates: boolean;
  requirePolicyApproval: boolean;
  maintainAuditLog: boolean;
  escalateHighValue: boolean;
}

export interface RecoveryFilters {
  status?: string; // "ALL" | RecoveryStatus
  category?: string;
  search?: string;
}

export interface DashboardData {
  kpis: {
    revenueAtRisk: number;
    recoveredRevenue: number;
    recoveryRate: number;
    incrementalRevenue: number;
    activeRecoveries: number;
    paymentsAtRisk: number;
  };
  funnel: { label: string; value: number; isCurrency?: boolean }[];
  aiVsStatic: {
    metric: string;
    static: string;
    ai: string;
    delta: string;
  }[];
  failureBreakdown: { category: FailureCategory; label: string; count: number; amount: number }[];
  recoveredSeries: { month: string; recovered: number; baseline: number }[];
}

export interface AnalyticsData {
  performance: { month: string; ai: number; static: number }[];
  byCategory: { label: string; recovered: number; rate: number }[];
  byMethod: { label: string; recovered: number; rate: number; share: number }[];
  byAttempt: { attempt: string; rate: number; recovered: number }[];
  avgTimeToRecoveryHours: { static: number; ai: number };
}

export interface SimulationInput {
  transactions: number;
  avgTransactionAmount: number;
  failureRate: number; // 0-1
  recoveryWindowDays: number;
}

export interface SimulationResult {
  id: string;
  input: SimulationInput;
  transactionsAnalyzed: number;
  failedPayments: number;
  revenueAtRisk: number;
  staticRecovered: number;
  staticRate: number;
  aiRecovered: number;
  aiRate: number;
  incrementalRevenue: number;
  actionBreakdown: { action: string; count: number; recovered: number }[];
  policyViolations: number;
  createdAt: string;
}

// Execution related types
export interface PolicyCheck {
  label: string;
  detail: string;
  passed: boolean;
  /** Escalating checks route to operator review instead of hard-blocking. */
  kind: PolicyCheckKind;
}

export type PolicyCheckKind = "pass" | "fail" | "escalate";

export interface ExecuteResult {
  payment: RecoveryPaymentDetail;
  policyChecks: PolicyCheck[];
}

// Backend response types (snake_case as returned by the API)

export interface DashboardResponse {
  kpis: {
    revenue_at_risk: number;
    recovered_revenue: number;
    recovery_rate: number;
    incremental_revenue: number;
    active_recoveries: number;
    payments_at_risk: number;
  };
  funnel: Array<{
    label: string;
    value: number;
    is_currency: boolean;
  }>;
  ai_vs_static: Array<{
    metric: string;
    static: string;
    ai: string;
    delta: string;
  }>;
  failure_breakdown: Array<{
    category: string;
    label: string;
    count: number;
    amount: number;
  }>;
  recovered_series: Array<{
    month: string;
    recovered: number;
    baseline: number;
  }>;
}

export interface RecoveryPaymentResponse {
  payment_id: string;
  customer_id: string;
  amount: number;
  currency: string; // "INR"
  failure_reason: string;
  failure_category: string; // FailureCategory
  retry_count: number;
  recovery_probability: number;
  confidence: number;
  recommended_action: string; // RecommendedAction
  recommended_at: string; // ISO string
  expected_recovery: number;
  status: string; // RecoveryStatus
  priority: string; // Priority
  payment_method: string; // PaymentMethod
  created_at: string; // ISO string
  failed_at: string; // ISO string
  next_action_at: string | null; // ISO string or null
}

export interface RecoveryPaymentDetailResponse extends RecoveryPaymentResponse {
  decision: {
    diagnosis: string | null;
    confidence: number;
    recovery_probability: number;
    recommended_action: string | null; // RecommendedAction | null
    expected_recovery: number;
    optimal_recovery_at: string | null; // ISO string
    model_version: string | null;
    signals: { name: string; value: string; impact: string; category: string }[];
    explanation: string | null;
    data_sufficiency: string | null;
    optimal_window: string | null;
  } | null;
  actions: Array<{
    id: string;
    action_type: string;
    status: string;
    scheduled_at: string | null;
    started_at: string | null;
    completed_at: string | null;
    external_reference: string | null;
  }>;
  customer: {
    external_customer_id: string;
    name: string | null;
    email: string | null;
    phone: string | null;
  } | null;
  provider_order_id: string | null;
  provider_status: string | null;
}

export interface AuditEventResponse {
  id: string;
  timestamp: string; // ISO string
  event_type: string; // AuditEventType
  category: string; // AuditCategory
  payment_id: string | null;
  summary: string;
  amount: number | null;
  metadata: Record<string, string>;
}

export interface AnalyticsResponse {
  performance: Array<{
    month: string;
    ai_rate: number;
    static_rate: number;
  }>;
  by_category: Array<{
    label: string;
    recovered: number;
    rate: number;
  }>;
  by_method: Array<{
    label: string;
    recovered: number;
    rate: number;
    share: number;
  }>;
  by_attempt: Array<{
    attempt: string;
    rate: number;
    recovered: number;
  }>;
  avg_time_to_recovery_hours: {
    static_hours: number;
    ai_hours: number;
  };
}

export interface SimulationResponse {
  id: string;
  transactions: number;
  average_amount: number;
  failure_rate: number;
  recovery_window_days: number;
  static_recovery_rate: number;
  ai_recovery_rate: number;
  static_recovered_revenue: number;
  ai_recovered_revenue: number;
  incremental_revenue: number;
  created_at: string; // ISO string
}

export interface PolicyResponse {
  maximum_retries: number;
  recovery_window_days: number;
  minimum_ai_confidence: number;
  high_value_threshold: number;
  failure_rules: Record<string, string>; // maps failure category to canonical action (e.g., "RETRY")
  prevent_duplicate_recovery: boolean;
  require_policy_approval: boolean;
  maintain_audit_log: boolean;
  escalate_high_value: boolean;
}

export interface PolicyUpsertRequest {
  maximum_retries: number;
  recovery_window_days: number;
  minimum_ai_confidence: number;
  high_value_threshold: number;
  prevent_duplicate_recovery: boolean;
  require_policy_approval: boolean;
  maintain_audit_log: boolean;
  escalate_high_value: boolean;
  failure_rules: Record<string, string>; // same as above
}

export interface SimulationCreateRequest {
  transactions: number;
  average_amount: number;
  failure_rate: number;
  recovery_window_days: number;
}

// Backend response types (these match what the backend actually returns)
export interface AnalyzeResponse {
  // This would match the backend's AnalyzeResponse schema
  // For now, we'll use RecoveryPaymentDetail since analyze returns updated decision
  // In a more complex implementation, this might be separate
  recovery_payment: RecoveryPaymentDetail;
}

export interface PolicyValidationResponse {
  payment_id: string;
  decision: string; // "APPROVED" | "BLOCKED" | "ESCALATED"
  allowed: boolean;
  reason: string;
  policy_version: string;
  checks: {
    label: string;
    detail: string;
    passed: boolean;
    severity: string; // maps to PolicyCheckKind
  }[];
  evaluated_at: string;
  policy_evaluation_id: string;
}

export interface ExecutionResponse {
  payment_id: string;
  decision: string; // "APPROVED" | "BLOCKED" | "ESCALATED"
  status: string; // "SCHEDULED" | "PROCESSING" | "CUSTOMER_ACTION_REQUIRED" | "FAILED" | "BLOCKED" | "ESCALATED"
  action: string | null;
  action_id: string | null;
  reason: string | null;
  message: string | null;
  policy_version: string | null;
  checks: {
    check_name: string;
    status: string; // "PASS" | "FAIL" | etc.
    message: string;
    severity: string;
    metadata: Record<string, string>;
  }[];
  external_reference: string | null;
}