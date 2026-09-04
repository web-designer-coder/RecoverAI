# RecoverAI Policy Engine + Safe Execution (Phase 5)

This document specifies the layer that sits between the AI engine and Razorpay:

```
AI RECOMMENDS  →  POLICY AUTHORIZES  →  EXECUTION EXECUTES  →  AUDIT RECORDS
(recoverai-v1)    (app/policy/)         (recovery_execution_     (audit_events,
                                          service.py)             append-only)
```

These four responsibilities are deliberately separate. The AI engine cannot execute
anything; the execution service cannot run a single provider operation without a fresh
policy authorization; nothing that happens escapes `audit_events`.

## Architecture

- **`app/policy/`** — standalone package, no FastAPI and no database access.
  - `models.py` — frozen dataclasses: `CheckStatus`, `PolicyCheckResult`,
    `PolicyDecision`, `PolicyContext`.
  - `checks.py` — pure, individually testable check functions. Identical inputs
    produce identical results (no I/O, no randomness).
  - `evaluator.py` — composes the checks in a fixed documented order into one
    `PolicyDecision`. It consumes an already-loaded context; it never queries the DB.
  - `service.py` — loads payment / failure / current decision / policy / existing
    actions, builds the `PolicyContext`, calls `evaluate()`, persists an immutable
    `PolicyEvaluation` row and writes `POLICY_CHECK` (+ block/escalate) audits.
- **`app/services/recovery_execution_service.py`** — the only path from approval to
  a provider call. There is intentionally NO lower-level method that executes without
  a fresh evaluation; authorization and execution cannot be decoupled by any caller
  (endpoint, background job or internal service).
- **`app/services/providers/payment_provider.py`** — the `PaymentProvider` protocol;
  the Phase 3 `RazorpayClient` is reused behind it (no second client exists).

## The twelve checks

Evaluated in this fixed order with **no short-circuiting** — every applicable check
runs so callers see all failures at once:

| # | Check | PASS when | FAIL/ESCALATE |
|---|---|---|---|
| 1 | `payment_state` | state ∈ {FAILED, QUEUED, NEEDS_ACTION} | FAIL for RECOVERED ("already recovered"), HALTED, AUTHORIZED, PROCESSING, SCHEDULED |
| 2 | `failure_exists` | a failure row exists | FAIL otherwise |
| 3 | `ai_decision_exists` | a recovery decision exists | FAIL — "Run analysis first" |
| 4 | `ai_decision_current` | decision is the latest version | FAIL — re-analysis required |
| 5 | `retry_limit` | `attempt_number < maximum_retries` | FAIL at limit |
| 6 | `recovery_window` | now ≤ failure time + window days (UTC only) | FAIL when expired |
| 7 | `ai_confidence` | confidence × 100 ≥ stored minimum % | FAIL below threshold |
| 8 | `action_compatibility` | recommendation ∈ intrinsically-compatible set for the failure category | FAIL — recommendation never silently replaced |
| 9 | `duplicate_recovery` | no active/succeeded action exists (when enabled) | FAIL if PENDING/VERIFYING_POLICY/APPROVED/SCHEDULED/PROCESSING/SUCCEEDED action exists |
| 10 | `high_value` | amount < threshold, or escalation disabled | ESCALATE (`HUMAN_APPROVAL_REQUIRED`) when ≥ threshold & enabled |
| 11 | `policy_approval` | explicit approval not required | ESCALATE — never auto-approved |
| 12 | *(implicit)* `policy_exists` | merchant policy configured | missing policy → immediate BLOCKED (`POLICY_NOT_CONFIGURED`) |

Rule-dependent checks still report `NOT_APPLICABLE` instead of being skipped when
their input is absent (e.g. no failure → `recovery_window` N/A).

### Retry semantics

`retry_count` counts **failed gateway attempts** (`payments.attempt_number`). Customer
notifications and payment-update requests are not retries — they never hit the gateway.
With `maximum_retries = 3`: attempts 0/1/2 pass, attempt 3 blocks.

### Compatibility matrix

Intrinsic compatibility only (the merchant's `failure_rules` matrix stays a tuning
input for the AI engine and is NOT force-matched here):

| Category | Compatible actions |
|---|---|
| INSUFFICIENT_FUNDS / NETWORK_FAILURE | RETRY, CUSTOMER_NOTIFICATION |
| EXPIRED_CARD | PAYMENT_UPDATE, STOP |
| INVALID_DETAILS | PAYMENT_UPDATE, CUSTOMER_NOTIFICATION, STOP |
| BANK_DECLINE | STOP, ESCALATE, PAYMENT_UPDATE |
| OTHER | any |

An incompatible recommendation BLOCKS execution with the original recommendation
surfaced in the check metadata — policy never substitutes its own preferred action.

## Decision precedence

```
any FAIL       → BLOCKED   (allowed = false)
else any ESCALATE → ESCALATED (allowed = false)
else           → APPROVED  (allowed = true)
```

Hard blocks can never be downgraded to escalation, and escalation never overrides a
block: **BLOCKED > ESCALATED > APPROVED**.

A missing merchant policy fails safe: the decision is BLOCKED with reason
`POLICY_NOT_CONFIGURED` — it is never silently approved.

## Versioning & traceability

- `policies.version` increments on every `PUT /api/policies`.
- Every evaluation is persisted as an immutable `policy_evaluations` row:
  `{payment_id, recovery_decision_id, policy_id, policy_version, decision, allowed,
  checks (JSONB), reason, evaluated_at}`.
- Every created `recovery_action.policy_evaluation_id` points at the exact evaluation
  that authorized it, which points at the policy version and AI decision version in
  force. Any execution can be traced end-to-end; historical evaluations are never
  rewritten by later policy changes.

## Execution state machine

```
PENDING ──► VERIFYING_POLICY ──► APPROVED ──► PROCESSING ──► SUCCEEDED
   │              │                  │             │
   │              │                  │             └──► FAILED
   ├─► SCHEDULED ─┘                  ├─► BLOCKED / CANCELLED
   └─► BLOCKED / ESCALATED / CANCELLED
                                     ├──► ESCALATED            (STOP/ESCALATE rec.)
                                     └──► CUSTOMER_ACTION_REQUIRED
```

All moves go through `validate_transition()`; anything unlisted raises
`InvalidTransitionError` and fails safely rather than being guessed. `apply_transition`
stamps `started_at` on entering PROCESSING and `completed_at` on terminal outcomes.
The operator stop endpoint cancels only PENDING/SCHEDULED actions through the same
machine — a PROCESSING or SUCCEEDED action is never silently rewritten, and no audit
history is ever deleted.

## Safe execution flow

```
load payment → load CURRENT AI decision → FRESH policy evaluation
  BLOCKED   → structured response, nothing written except the audit/evaluation trail
  ESCALATED → structured response, nothing executed
  APPROVED  → PENDING→APPROVED transition
                customer-facing action → CUSTOMER_ACTION_REQUIRED (payment NEEDS_ACTION)
                ESCALATE/STOP rec.    → terminal ESCALATED / BLOCKED
                optimal_recovery_at > now → SCHEDULED (+ scheduled_at, next_action_at)
                else                  → PROCESSING (payment PROCESSING)
                                            → provider op → persist result → audit → commit
```

Provider outcomes map to:

| Provider result | Action state | Payment state | Audit |
|---|---|---|---|
| PROCESSING (payment link created) | PROCESSING + external_reference | PROCESSING | RECOVERY_EXECUTED |
| SUCCEEDED (confirmed) | SUCCEEDED | RECOVERED | PAYMENT_RECOVERED |
| CUSTOMER_ACTION_REQUIRED | CUSTOMER_ACTION_REQUIRED | NEEDS_ACTION | CUSTOMER_NOTIFIED |
| exception / invalid response / unavailable factory | FAILED + failure_reason | back to FAILED | RECOVERY_FAILED |

**Money state follows provider confirmation only.** A payment is marked RECOVERED
exclusively by the Phase 3 webhook ingestion path (`payment.captured`), never because
a link was created.

## What Razorpay actually supports (and what we implement)

There is no generic server-side "retry a failed payment" API. The genuinely supported,
safe operation implemented here is **creating a Payment Link**
(`POST /v1/payment_links`). A link moves no money itself; the customer completes it and
the outcome arrives via webhook. Therefore:

- RETRY → payment-link creation → action/payment PROCESSING until webhook confirmation.
- PAYMENT_UPDATE / CUSTOMER_NOTIFICATION → recorded as CUSTOMER_ACTION_REQUIRED; we do
  not pretend to message customers or edit instruments server-side.
- Anything unsupported returns honestly (`CUSTOMER_ACTION_REQUIRED` or ESCALATED) —
  correctness over demo theatrics.

## Idempotency & concurrency

- Optional client-supplied idempotency key (or default
  `{payment}:{decision_id}:{action}`), UNIQUE at the database level.
- A replayed key returns the existing action's recorded state (read-only — no new
  action, no provider call, hence no policy bypass).
- Duplicate protection is enforced by a partial unique index
  `uq_active_action_per_payment ON recovery_actions(payment_id) WHERE status IN
  ('PENDING','VERIFYING_POLICY','APPROVED','SCHEDULED','PROCESSING')` — two concurrent
  executions cannot both create active actions. An insert race resolves to an
  idempotent replay or a structured 409 `EXECUTION_CONFLICT`; no Python locks.

## Audit model

Events (all append-only, category POLICY or EXECUTION, actor SYSTEM):

- `POLICY_CHECK` — every evaluation (metadata: decision_id, policy_version,
  model_version, full check list; blocks/escalations also emit `POLICY_BLOCKED` /
  `POLICY_ESCALATED`).
- `RECOVERY_SCHEDULED`, `RECOVERY_PROCESSING`, `RECOVERY_EXECUTED`,
  `PAYMENT_RECOVERED`, `RECOVERY_FAILED` — the execution lifecycle, each carrying
  action_id, policy_evaluation_id and (where applicable) the opaque provider reference.

No secrets, credentials or chain-of-thought are ever logged or audited — only
structured decisions, check results and opaque references.

## Known limitations

- No human-approval platform exists yet: `require_policy_approval` always escalates.
- Scheduled recoveries persist intent only; there is no background worker in this phase.
- Customer notification/payment-update flows stop at recording the required action.
- Only Test Mode Razorpay operations are implemented; live money movement is out of scope.
