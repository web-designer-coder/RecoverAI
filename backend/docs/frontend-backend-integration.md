# Frontend-Backend Integration Guide

## Overview
This document provides a comprehensive guide for integrating the RecoverAI frontend with the FastAPI backend in Phase 7.

## Prerequisites
1. Backend running on `http://localhost:8000` (or configured port)
2. Database seeded with demo data (`python -m app.seed`)
3. Frontend development server running

## API Base URL Configuration

Create a `.env.local` file in the frontend root with:
```
VITE_API_BASE_URL=http://localhost:8000/api
```

In frontend code, use:
```typescript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
```

Never hardcode URLs or expose secrets through VITE_ variables.

## Central API Client Implementation

Replace `src/lib/api.ts` with a proper API client that:
1. Uses `fetch()` instead of mock data
2. Handles authentication headers
3. Transforms data between backend (snake_case) and frontend (camelCase)
4. Handles errors consistently
5. Provides typed API functions

### API Client Structure
```typescript
// src/lib/api.ts
import type { 
  DashboardData,
  RecoveryPayment,
  RecoveryPaymentDetail,
  AuditEvent,
  PolicyRules,
  SimulationInput,
  SimulationResult,
  // ... other types
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      // Add auth token here when available
    },
    ...options
  });

  if (!response.ok) {
    const errorData = await response.json();
    throw new ApiError(
      errorData.error?.code || 'UNKNOWN_ERROR',
      errorData.error?.message || 'An unknown error occurred',
      response.status
    );
  }

  return response.json();
}

// Transform helper functions
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
  constructor(
    public code: string,
    public message: string,
    public status: number
  ) {
    super(message);
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

  // ... other endpoints
};

// Transformation functions
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
    recommended_at: backend.recommended_at?.toISOString() ?? '',
    expected_recovery: backend.expected_recovery,
    status: backend.status as RecoveryStatus,
    priority: backend.priority as Priority,
    payment_method: backend.payment_method as PaymentMethod,
    created_at: backend.created_at.toISOString(),
    failed_at: backend.failed_at.toISOString(),
    next_action_at: backend.next_action_at?.toISOString() ?? null
  };
}

// Similar transformation functions for other endpoints
```

## Authentication Integration

### Current State
- Backend uses mock merchant resolution via `MerchantId` dependency
- No real authentication implemented in Phase 2
- Frontend currently uses mock auth in `src/lib/auth.ts`

### Integration Approach
1. Keep frontend auth boundary intact for now
2. When real auth is available, replace mock functions with actual API calls
3. Protected routes should check auth state before making API calls

### Protected Routes
These routes should require authentication:
- `/app/*` (all app routes)
- Specifically: `/app/dashboard`, `/app/recovery`, `/app/simulator`, `/app/analytics`, `/app/audit`, `/app/policies`, `/app/settings`

Public routes:
- `/`
- `/login`
- `/signup`

## State Management & Data Fetching

### React Query Implementation
Since React Query is already installed, use it for server state management:

```typescript
// src/lib/hooks.ts or custom hooks
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

export function useDashboard() {
  return useQuery({
    queryKey: ['dashboard'],
    queryFn: api.getDashboard,
    staleTime: 5 * 60 * 1000 // 5 minutes
  });
}

export function useRecoveries(filters: RecoveryFilters = {}) {
  return useQuery({
    queryKey: ['recoveries', filters],
    queryFn: () => api.getRecoveries(filters),
    staleTime: 60 * 1000 // 1 minute
  });
}

export function useRecovery(id: string) {
  return useQuery({
    queryKey: ['recovery', id],
    queryFn: () => api.getRecovery(id),
    enabled: !!id
  });
}

export const useAnalyzeRecovery = () => {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: api.analyzeRecovery,
    onSuccess: (_, paymentId) => {
      queryClient.invalidateQueries({ queryKey: ['recovery', paymentId] });
      queryClient.invalidateQueries({ queryKey: ['recoveries'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    }
  });
};

// Similar mutations for execute, stop, validatePolicy, etc.
```

## Component Integration Guidelines

### Dashboard Integration
Replace mock data calls in `src/routes/app/dashboard.tsx`:
```typescript
// Before
const dashboardData = buildDashboard(store.payments);

// After
const { data: dashboardData, isLoading, error } = useDashboard();
```

### Recovery Queue Integration
Replace mock data calls in `src/routes/app/recovery.tsx`:
```typescript
// Before
const recoveries = getRecoveries(filters);

// After
const { data: recoveries, isLoading, error } = useRecoveries(filters);
```

### Recovery Detail Integration
Replace mock data calls in `src/routes/app/recovery/[paymentId].tsx`:
```typescript
// Before
const recovery = getRecovery(paymentId);

// After
const { data: recovery, isLoading, error } = useRecovery(paymentId);
```

### Simulation Integration
Replace mock data calls in `src/routes/app/simulator.tsx`:
```typescript
// Before
const result = await runSimulation(input);

// After
const { data: result, isLoading, error } = useMutation({
  mutationFn: api.runSimulation
});

// In form handler:
mutate(input);
```

## Error Handling

Create a consistent error handling approach:
```typescript
// src/lib/error-utils.ts
export function formatApiError(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'PAYMENT_NOT_FOUND':
        return 'Payment not found';
      case 'NO_FAILURE_DATA':
        return 'No failure data available for analysis';
      case 'ALREADY_RECOVERED':
        return 'Payment has already been recovered';
      case 'POLICY_NOT_CONFIGURED':
        return 'Recovery policies not configured';
      case 'VALIDATION_ERROR':
        return error.message;
      default:
        return error.message || 'An unexpected error occurred';
    }
  }
  
  if (error instanceof Error) {
    return error.message;
  }
  
  return 'An unknown error occurred';
}
```

## Loading & Empty States

### Loading States
Show skeletons or spinners while data is loading:
```typescript
{isLoading ? (
  <div className="animate-pulse">Loading...</div>
) : data ? (
  // Render data
) : (
  <div>No data available</div>
)}
```

### Error States
Display user-friendly error messages:
```typescript
{error ? (
  <div className="text-destructive">
    {formatApiError(error)}
    <button onClick={retry}>Try again</button>
  </div>
) : null}
```

## Data Transformation Guidelines

### Money Values
- Backend returns floats for money (converted from Decimal)
- Frontend should display as formatted currency
- Use existing format helpers in `src/lib/format.ts`

### Dates/Times
- Backend returns ISO strings
- Frontend should convert to local time for display
- Use consistent date formatting

### Enums
- Backend returns strings
- Frontend should map to TypeScript enums
- Create bidirectional mapping functions

## Testing

### Frontend Tests
1. Test API client transformation functions
2. Test React query hooks
3. Test component integration with mocked API responses
4. Test error handling scenarios

### Backend Tests
Ensure all existing tests still pass:
```
pytest
```

## Development Workflow

### Terminal 1 - Backend
```bash
cd backend
# Check .env file exists with correct settings
uvicorn app.main:app --reload
```

### Terminal 2 - Frontend
```bash
# Ensure .env.local exists with VITE_API_BASE_URL
npm run dev
```

## Verification Checklist

### Core Functionality
- [ ] Dashboard shows real backend data
- [ ] Recovery queue lists real payments from backend
- [ ] Recovery detail shows real AI decisions and actions
- [ ] Analyze button calls backend and updates decision
- [ ] Policy validation shows real policy checks
- [ ] Execute recovery shows real execution flow
- [ ] Stop recovery properly halts recovery
- [ ] Analytics shows real computed metrics
- [ ] Audit trail shows real events
- [ ] Simulation runs with real backend engine
- [ ] Policies page shows and updates real policies

### State Management
- [ ] Loading states shown during API calls
- [ ] Error states handled gracefully
- [ ] Empty states handled appropriately
- [ ] Successful mutations trigger cache invalidation
- [ ] Related data refreshes after mutations

### Security
- [ ] No secrets exposed in frontend code
- [ ] No sensitive data in URLs or logs
- [ ] CORS properly configured
- [ ] Authentication boundaries respected

### Performance
- [ ] React Query caching used appropriately
- [ ] Requests debounced where needed (search)
- [ ] Pagination implemented for large datasets
- [ ] No unnecessary duplicate requests

### Edge Cases
- [ ] 404 cases handled (payment not found)
- [ ] 409 cases handled (conflicts like already recovered)
- [ ] Validation errors (422) shown to user
- [ ] Network errors handled gracefully
- [ ] 500 errors shown as generic backend error

## Known Limitations

### Phase 2 Backend Limitations
1. No real authentication - uses demo merchant resolution
2. No actual Razorpay integration - simulations only
3. Limited provider operations in execution service
4. Simulation engine is simplified (will be enhanced in later phases)

### Frontend Workarounds
1. Maintain mock auth boundary until real auth available
2. Handle backend limitations gracefully in UI
3. Don't implement frontend business logic that should be backend-only
4. Clearly separate demo/marketing content from real data views

## Deployment Notes

When moving to production:
1. Update VITE_API_BASE_URL to production endpoint
2. Ensure CORS configuration includes production frontend domain
3. Set proper environment variables in backend
4. Ensure database is properly seeded/provisioned
5. Verify authentication system is working