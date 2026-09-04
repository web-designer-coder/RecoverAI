# API Mapping Documentation

## Overview
This document maps frontend TypeScript interfaces to backend Pydantic schemas for Phase 7 integration.

## API Endpoints Mapping

### Dashboard
- **Frontend**: `getDashboard()` → `GET /api/dashboard`
- **Response**: 
  - Frontend: `DashboardData`
  - Backend: `DashboardResponse`

### Recoveries Queue
- **Frontend**: `getRecoveries(filters)` → `GET /api/recoveries`
- **Response**:
  - Frontend: `RecoveryPayment[]`
  - Backend: `list[RecoveryPaymentResponse]`

### Recovery Detail
- **Frontend**: `getRecovery(id)` → `GET /api/recoveries/{payment_id}`
- **Response**:
  - Frontend: `RecoveryPayment | null`
  - Backend: `RecoveryPaymentDetailResponse`

### Recovery Audit
- **Frontend**: (to be implemented) → `GET /api/recoveries/{payment_id}/audit`
- **Response**:
  - Frontend: `AuditEvent[]`
  - Backend: `list[AuditEventResponse]`

### Analyze Recovery
- **Frontend**: `analyzeRecovery(id)` → `POST /api/recoveries/{payment_id}/analyze`
- **Request**: None
- **Response**:
  - Frontend: `RecoveryPayment | null`
  - Backend: `AnalyzeResponse`

### Validate Policy
- **Frontend**: `validatePolicy(id)` → `POST /api/recoveries/{payment_id}/validate-policy`
- **Request**: None
- **Response**:
  - Frontend: To be defined (likely custom type)
  - Backend: `PolicyValidationResponse`

### Execute Recovery
- **Frontend**: `executeRecovery(id)` → `POST /api/recoveries/{payment_id}/execute`
- **Request**: Optional idempotency key
- **Response**:
  - Frontend: `ExecuteResult | null`
  - Backend: `ExecutionResponse`

### Stop Recovery
- **Frontend**: `stopRecovery(id)` → `POST /api/recoveries/{payment_id}/stop`
- **Request**: None
- **Response**:
  - Frontend: `RecoveryPayment | null`
  - Backend: `RecoveryPaymentResponse`

### Analytics
- **Frontend**: `getAnalytics()` → `GET /api/analytics`
- **Response**:
  - Frontend: `AnalyticsData`
  - Backend: `AnalyticsResponse`

### Audit
- **Frontend**: `getAudit(category?)` → `GET /api/audit`
- **Response**:
  - Frontend: `AuditEvent[]`
  - Backend: `list[AuditEventResponse]`

### Simulation
- **Frontend**: `runSimulation(input)` → `POST /api/simulations`
- **Request**:
  - Frontend: `SimulationInput`
  - Backend: `SimulationCreateRequest`
- **Response**:
  - Frontend: `SimulationResult`
  - Backend: `SimulationResponse`

### Policies
- **Frontend**: `getPolicies()` → `GET /api/policies`
- **Response**:
  - Frontend: `PolicyRules`
  - Backend: `PolicyResponse`
- **Frontend**: `updatePolicies(policies)` → `PUT /api/policies`
- **Request**:
  - Frontend: `PolicyRules`
  - Backend: `PolicyUpsertRequest`

## Schema Transformations

### Common Transformations
1. **Case Conversion**: Backend uses snake_case, frontend uses camelCase
2. **Number Types**: 
   - Backend uses Decimal for monetary values internally, converts to float for API
   - Frontend uses number for all numeric values
3. **Date Strings**: 
   - Backend returns ISO string datetime objects
   - Frontend expects ISO string dates

### Specific Mappings

#### Policy Schemas
Frontend `PolicyRules`:
```typescript
{
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
```

Backend `PolicyUpsertRequest`:
```python
{
  maximum_retries: int;
  recovery_window_days: int;
  minimum_ai_confidence: Decimal;
  high_value_threshold: Decimal;
  prevent_duplicate_recovery: bool;
  require_policy_approval: bool;
  maintain_audit_log: bool;
  escalate_high_value: bool;
  failure_rules: dict[FailureCategory, str];  # Canonical actions
}
```

Backend `PolicyResponse`:
```python
{
  policy_version: int;
  maximum_retries: int;
  recovery_window_days: int;
  minimum_ai_confidence: float;
  high_value_threshold: float;
  prevent_duplicate_recovery: bool;
  require_policy_approval: bool;
  maintain_audit_log: bool;
  escalate_high_value: bool;
  failure_rules: dict[FailureCategory, str];  # Canonical actions
}
```

Transform needed:
- Convert snake_case to camelCase
- Convert failure_rules from canonical actions to frontend RecommendedAction aliases
- Handle policy_version field (backend has it, frontend doesn't currently expect it)

#### Payment Schemas
Frontend `RecoveryPayment`:
```typescript
{
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
```

Backend `RecoveryPaymentResponse`:
```python
{
  payment_id: str;
  customer_id: str;
  amount: float;
  currency: str;
  payment_method: str;
  status: str;
  priority: str;
  retry_count: int;
  failure_reason: str;
  failure_category: str;
  recovery_probability: float;
  confidence: float;
  recommended_action: str;
  recommended_at: datetime | None;
  expected_recovery: float;
  created_at: datetime;
  failed_at: datetime;
  next_action_at: datetime | None;
}
```

Transform needed:
- Convert snake_case to camelCase
- Convert string enums to actual enum types
- Handle nullable datetime fields
- Convert amount/expected_recovery from float to number (no transformation needed)

Backend `RecoveryPaymentDetailResponse` extends Response with:
```python
{
  decision: DecisionInfo | None;
  actions: list[ActionInfo];
}
```

Where `DecisionInfo` and `ActionInfo` contain additional nested objects.

#### Simulation Schemas
Frontend `SimulationInput`:
```typescript
{
  transactions: number;
  avgTransactionAmount: number;
  failureRate: number; // 0-1
  recoveryWindowDays: number;
}
```

Backend `SimulationCreateRequest`:
```python
{
  transactions: int;
  average_amount: Decimal;
  failure_rate: Decimal;
  recovery_window_days: int;
}
```

Frontend `SimulationResult`:
```typescript
{
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
```

Backend `SimulationResponse`:
```python
{
  id: str;
  transactions: int;
  average_amount: float;
  failure_rate: float;
  recovery_window_days: int;
  static_recovery_rate: float;
  ai_recovery_rate: float;
  static_recovered_revenue: float;
  ai_recovered_revenue: float;
  incremental_revenue: float;
  created_at: datetime;
}
```

Transform needed:
- Convert snake_case to camelCase
- Map backend response fields to frontend interface (different field names/structure)
- For simulations, the backend response structure is different from frontend expectation
- Backend returns aggregate metrics, frontend expects detailed breakdown including action breakdown

#### Audit Schemas
Frontend `AuditEvent`:
```typescript
{
  id: string;
  timestamp: string;
  type: AuditEventType;
  category: AuditCategory;
  payment_id: string;
  summary: string;
  amount?: number;
  detail: Record<string, string>;
}
```

Backend `AuditEventResponse`:
```python
{
  id: str;
  timestamp: datetime;
  event_type: str;
  category: str;
  actor_type: str;
  payment_id: str | None;
  summary: str;
  amount: float | None;
  metadata: dict;
}
```

Transform needed:
- Convert snake_case to camelCase
- Map event_type to type, category to category
- Handle optional payment_id
- Map metadata to detail

#### Analytics Schemas
Frontend `AnalyticsData`:
```typescript
{
  performance: { month: string; ai: number; static: number }[];
  byCategory: { label: string; recovered: number; rate: number }[];
  byMethod: { label: string; recovered: number; rate: number; share: number }[];
  byAttempt: { attempt: string; rate: number; recovered: number }[];
  avgTimeToRecoveryHours: { static: number; ai: number };
}
```

Backend `AnalyticsResponse`:
```python
{
  performance: list[PerformancePoint];
  by_category: list[CategoryRecovery];
  by_method: list[MethodRecovery];
  by_attempt: list[AttemptRecovery];
  avg_time_to_recovery_hours: AvgTimeToRecovery;
  simulations: Optional[List[SimulationResult]];
}
```

Where the nested objects have different field names.

Transform needed:
- Convert snake_case to camelCase
- Map nested object fields:
  - PerformancePoint: month, ai_rate, static_rate → {month, ai, static}
  - CategoryRecovery: label, recovered, rate → {label, recovered, rate}
  - MethodRecovery: label, recovered, rate, share → {label, recovered, rate, share}
  - AttemptRecovery: attempt, rate, recovered → {attempt, rate, recovered}
  - AvgTimeToRecovery: static_hours, ai_hours → {static, ai}

## Error Response Format

Backend returns:
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message"
  }
}
```

Frontend should handle this format consistently.

## Authentication
Backend uses dependency injection for merchant resolution:
- `MerchantId` dependency resolves to demo merchant ID
- No real authentication implemented in Phase 2
- Frontend mock auth should be replaced with proper integration when available