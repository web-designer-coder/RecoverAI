# RecoverAI Backend

FastAPI + PostgreSQL backend for RecoverAI, an Indian payment-recovery
operations platform (₹ / UPI context).

**Current status — Phase 5 complete.** The TanStack Start frontend is still NOT
connected (it runs on `src/lib/api.ts` mocks until Phase 7). Implemented:
foundation (Phase 2), Razorpay Test Mode webhook ingestion + reconciliation
(Phase 3), the deterministic `recoverai-v1` intelligence engine (Phase 4), and
the policy engine + safe execution layer (Phase 5). The simulation engine is a
deliberate `501` boundary until Phase 6.

## Architecture

```
route (app/api/*)          HTTP boundary: validation via Pydantic, error envelope
  └─ service (app/services/*)   business assembly, external-id translation
       └─ repository (app/repositories/*)  all SQL lives here
            └─ SQLAlchemy 2.x models (app/models/*)
                 └─ PostgreSQL (via psycopg3, migrations via Alembic)
```

- **Money**: every monetary column is `NUMERIC` (`NUMERIC(14,2)` for amounts in
  rupees — ₹8,499 is stored as `8499.00`; `NUMERIC(16,2)` for aggregate revenue).
  Python side uses `Decimal` end-to-end; floats never touch money at rest.
  Paise-level integer storage is deliberately deferred until the Razorpay
  integration phase (Razorpay speaks paise) — the mapping will be a pure
  conversion at the gateway boundary.
- **Identity**: internal UUID primary keys; provider-facing identifiers
  (`PAY_82931`, `CUST_0482`) live in separate `external_*_id` columns with a
  unique constraint per merchant.
- **Enums**: stored as plain VARCHARs (`native_enum=False`) so adding values
  never requires an `ALTER TYPE`.
- **Audit trail** (`audit_events`): append-only at three levels — the
  repository exposes only insert/read methods, a DB trigger rejects
  UPDATE/DELETE with SQLSTATE `55006`, and payment deletion only nulls the
  reference (`ON DELETE SET NULL`). Only the explicit seed-reset path bypasses
  the trigger (`session_replication_role = replica`).
- **Errors**: uniform envelope `{"error": {"code", "message"}}`; internals are
  logged server-side, never returned to clients.

## Domain model

| Table | Purpose |
|---|---|
| `merchants` | Tenant root (single demo merchant in this phase) |
| `customers` | Per-merchant customers, keyed by external id |
| `payments` | Failed-payment pipeline records (status, method, attempts, priority) |
| `payment_failures` | One row per observed failure (code, reason, category) |
| `recovery_decisions` | AI diagnosis output (confidence, probability, recommended action) |
| `recovery_actions` | Executed/scheduled recovery attempts |
| `policies` | Per-merchant recovery policy (retry caps, thresholds, failure rules) |
| `audit_events` | Append-only operational history |
| `simulations` | Stored simulation inputs/results (engine = Phase 6) |

## API surface

Read APIs (implemented against PostgreSQL):

- `GET /api/health` — app + database health
- `GET /api/dashboard` — KPIs, funnel, AI-vs-static comparison, failure breakdown
- `GET /api/recoveries?status=&category=&search=` — recovery queue
- `GET /api/recoveries/{external_payment_id}` — detail with decision + actions
- `GET /api/recoveries/{id}/audit` — per-payment audit trail
- `GET /api/analytics` — monthly/category/method/attempt analytics
- `GET /api/audit?category=&limit=` — global audit log
- `GET /api/policies` — merchant policy (with `policy_version`)
- `PUT /api/policies` — validated update; every change bumps `policy_version`
- `GET /api/simulations` — stored simulation records
- `POST /api/recoveries/{id}/stop` — real operator transition (HALTED + audit event)
- `POST /api/recoveries/{id}/analyze` — AI analysis (`recoverai-v1`, versioned)
- `POST /api/recoveries/{id}/validate-policy` — twelve-check policy evaluation,
  persisted immutably (Phase 5)
- `POST /api/recoveries/{id}/execute?idempotency_key=…` — policy-checked safe
  execution (Phase 5)

Explicit phase boundary (returns `501 NOT_IMPLEMENTED_YET`, no fake data):

- `POST /api/simulations` — batch simulation engine, Phase 6

The frontend-facing field names (`payment_id`, `retry_count`, `NOTIFY`,
`failed_at`, …) mirror `src/lib/api.ts` so Phase 7 is a thin fetch swap.
Mapping document: [`docs/api-mapping.md`](docs/api-mapping.md).

## Getting started

Prerequisites: Python 3.12+, PostgreSQL 14+ (a Docker container works well),
Docker Desktop if using containers.

```powershell
# 1. PostgreSQL (example: docker)
docker run -d --name recoverai-postgres -e POSTGRES_PASSWORD=recoverai_dev `
  -e POSTGRES_DB=recoverai -p 5432:5432 postgres:16-alpine
docker exec recoverai-postgres psql -U postgres -c "CREATE DATABASE recoverai_test;"

# 2. Install dependencies
cd backend
pip install -r requirements.txt

# 3. Configure environment (never commit .env)
Copy-Item .env.example .env   # then edit DATABASE_URL etc.

# 4. Migrate from a clean database
python -m alembic upgrade head          # apply
python -m alembic downgrade base        # roll back (development)

# 5. Seed the demo environment (mirrors src/lib/mock-data.ts)
python -m app.seed            # no-op if data exists
python -m app.seed --reset    # wipe demo rows and reseed

# 6. Run the API
uvicorn app.main:app --reload     # docs at http://127.0.0.1:8000/docs
```

## Tests

```powershell
python -m pytest tests -q
```

Tests run against `recoverai_test` (set in `tests/conftest.py`) and each test
is rolled back inside a transaction, so development data can never be touched
by the suite. Coverage includes the ten Phase-2 acceptance cases plus a check
that the database itself blocks audit mutation.

## Environment variables

| Variable | Purpose | Default (dev) |
|---|---|---|
| `DATABASE_URL` | PostgreSQL URL (`postgresql+psycopg://…`) | local dev container |
| `APP_ENV` | `dev` / `prod` marker surfaced by `/api/health` | `dev` |
| `API_HOST` / `API_PORT` | uvicorn bind settings | `127.0.0.1` / `8000` |
| `CORS_ORIGINS` | comma-separated explicit origins (**never** `*`) | `http://localhost:3000` |
| `LOG_LEVEL` | logging level | `INFO` |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | Razorpay **Test Mode** API keys (provider fetches) | unset |
| `RAZORPAY_WEBHOOK_SECRET` | webhook signature secret (separate credential) | unset |

Real secrets stay out of git — `.gitignore` excludes `.env`.

## Logging discipline

Request logs contain method, path, status and duration only. Passwords, API
keys, webhook secrets and full payment credentials must never be logged; error
handlers return generic messages to clients while details go to server logs.

## Payment ingestion & Razorpay integration (Phase 3)

Razorpay **Test Mode only** — live credentials are never used.

### Webhook pipeline

```
Razorpay Test Mode
  │  POST /api/webhooks/razorpay   (x-razorpay-signature, x-razorpay-event-id)
  ▼
raw-body HMAC-SHA256 verification  → 400 INVALID_SIGNATURE on failure
  ▼
JSON parse + shape validation      → 400 INVALID_PAYLOAD on failure
  ▼
webhook_events registration        → duplicate event id ⇒ 200 DUPLICATE_EVENT,
  (UNIQUE provider+event_id)         nothing reprocessed
  ▼
event dispatcher
  ├─ payment.failed    → payment upsert + failure row + PAYMENT_FAILED audit
  ├─ payment.captured  → RECOVERED + PAYMENT_RECOVERED audit (once)
  ├─ payment.authorized→ AUTHORIZED (NOT recovered — funds held, not received)
  └─ anything else     → 200 UNSUPPORTED_EVENT (order.paid intentionally deferred:
                          captured events already correlate payments by id)
```

Handler writes and the ledger update commit atomically; on failure everything
rolls back, the ledger row is marked `FAILED`, and the endpoint answers 5xx so
Razorpay retries. Out-of-order events are safe: transitions follow a fixed
precedence (`RECOVERED > AUTHORIZED > pipeline states > FAILED`); a stale
delivery is recorded as `STALE_IGNORED` without touching the payment.

Money arrives in paise (849900 → ₹8499.00) and is converted exactly once, in
`app/utils/money.py` (ISO 4217 minor-unit aware). Failure reasons are
normalized to domain categories by `app/utils/failure_classification.py`
(unmatched ⇒ OTHER). The webhook ledger stores only a SHA-256 payload hash —
never card data, CVV or full payloads.

### Environment variables

| Variable | Purpose |
|---|---|
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | Test Mode API keys for provider fetches (reconciliation). Not used for webhooks. |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook-specific secret from the dashboard — different credential from KEY_SECRET; used ONLY for signature verification. |

The backend starts fine with these unset; unrelated features and tests run
without them.

### Razorpay Dashboard setup (Test Mode)

1. Log in to the Razorpay Dashboard and switch to **Test Mode**.
2. Settings → API Keys → generate Test Mode keys → put them in `.env`
   (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`).
3. Settings → Webhooks → add a webhook URL pointing at your running backend
   (see local testing below) — path `/api/webhooks/razorpay`.
4. Set the webhook secret; copy the same value into `RAZORPAY_WEBHOOK_SECRET`.
5. Enable events: `payment.failed`, `payment.captured` (optionally
   `payment.authorized`). Nothing else is needed.
6. Start the backend: `uvicorn app.main:app --reload`.
7. If localhost cannot receive deliveries, expose it via a secure tunnel
   (e.g. `ngrok http 8000` or Cloudflare Tunnel) and register the public URL.
   Never commit tunnel credentials or URLs containing secrets.
8. Trigger a test payment (Test Mode checkout / test cards) to produce events.
9. Watch ingestion in the server log (`Webhook <id> <event> processed: ...`)
   and verify rows:

```sql
SELECT external_payment_id, status, amount, provider_status FROM payments ORDER BY created_at DESC;
SELECT event_type, summary FROM audit_events WHERE category = 'INGESTION';
SELECT provider_event_id, event_type, status, result FROM webhook_events;
```

10. Confirm the matching audit event exists (category INGESTION / RESULT).

If you cannot use a tunnel at all, signed fixtures drive the same code path —
`tests/rzp_fixtures.py` builds realistic payloads and HMAC signatures, which
is exactly how the automated suite exercises the endpoint.

### Reconciliation

`PaymentReconciliationService` (services/payment_reconciliation_service.py)
fetches current truth via `GET /v1/payments/:id`, compares it to local state
using the same precedence rules as ingestion, applies safe updates and audits
changes as PROVIDER_SYNC. It is a reusable boundary — no scheduled worker in
this phase.

## AI recovery intelligence (Phase 4)

`POST /api/recoveries/{payment_id}/analyze` turns one persisted failure into a
deterministic, explainable, persisted recommendation. Full formula and worked
example: [`docs/recovery-intelligence.md`](docs/recovery-intelligence.md).

```
failure ──► features (leakage-safe SQL aggregates) ──► diagnosis ──► probability
        ──► confidence ──► action ──► timing windows (max expected value) ──► explanation
        ──► RecoveryDecision (append-only versions) + 3 AI audit events
```

Key properties:

- **recoverai-v1** — transparent additive scoring; every contribution is stored
  as a structured signal (`name/value/impact/category`). No randomness, no LLM
  in the decision path; the optional LLM layer can only rewrite prose.
- **Leakage-safe history** — only failures strictly before the current failure,
  current payment excluded from its own history; missing evidence contributes
  exactly zero (never faked).
- **Probability ≠ confidence** — odds of success vs how sure the model is;
  data sufficiency HIGH/MEDIUM/LOW drives confidence only.
- **Windows NOW/+12H/+1D/+2D** — winner maximizes amount × probability
  (Decimal ERV); ties break earliest. Hard declines cap at 0.15 → STOP.
- **Versioning** — each analysis appends a new decision row with a monotonic
  per-payment `version_number`; current = highest version.

Try it:

```bash
curl -X POST http://localhost:8000/api/recoveries/PAY_82931/analyze   # analyze (new version each call)
curl -X POST http://localhost:8000/api/recoveries/PAY_82845/analyze   # 409 ALREADY_RECOVERED
```

The engine only recommends — no retry is executed and no policy is read.

## Policy engine & safe execution (Phase 5)

Full specification: [`docs/policy-engine.md`](docs/policy-engine.md).

```
AI RECOMMENDS  →  POLICY AUTHORIZES  →  EXECUTION EXECUTES  →  AUDIT RECORDS
(app/intelligence) (app/policy/)       (recovery_execution_    (audit_events,
                                        service.py)             append-only)
```

Key properties:

- **Twelve deterministic checks, no short-circuiting** — payment state,
  failure existence, decision presence/currency, retry limit, recovery window
  (UTC), AI confidence, action compatibility, duplicate protection, high-value,
  explicit approval, and the implicit `policy_exists` fail-safe.
- **Precedence** — `BLOCKED > ESCALATED > APPROVED`; hard blocks are never
  downgraded; a missing policy BLOCKS (`POLICY_NOT_CONFIGURED`), never approves.
- **Traceability** — every evaluation lands in an immutable `policy_evaluations`
  row; every created action points at its authorizing evaluation, which points
  at the exact policy version and AI decision version in force.
- **State machine** — all action moves validated (`PENDING→APPROVED→…`);
  invalid transitions raise and fail safely rather than being guessed.
- **Honest Razorpay boundary** — a RETRY creates a Payment Link
  (`POST /v1/payment_links`, a genuinely supported operation); money moves only
  when the customer pays and the Phase 3 webhook confirms. Nothing is ever
  marked RECOVERED by link creation. Customer-facing actions are recorded as
  `CUSTOMER_ACTION_REQUIRED`, never faked server-side.
- **Idempotency & concurrency** — UNIQUE idempotency key + partial unique
  active-action-per-payment index; replays are read-only; insert races resolve
  to a replay or structured 409 `EXECUTION_CONFLICT`. No Python locks.

Try it:

```bash
curl -X POST http://localhost:8000/api/recoveries/PAY_82931/validate-policy
curl -X POST "http://localhost:8000/api/recoveries/PAY_82931/execute?idempotency_key=demo-1"
curl -X PUT http://localhost:8000/api/policies   # bumps policy_version; history untouched
```

## Current limitations (by design)

- No authentication — single demo tenant resolved by convention; JWT/auth comes later.
- No human-approval platform: `require_policy_approval` always escalates.
- Scheduled recoveries persist intent only — no background worker yet.
- No customer notification infrastructure; notification/update flows stop at
  recording the required action.
- Razorpay operations are Test Mode only; no live money movement.
- Webhook ingestion is Test Mode only; no refunds/disputes handling.
- Frontend remains mock-connected; this API is not consumed yet.
- Simulation engine remains a 501 boundary until Phase 6.
- Analytics compare against documented business benchmark constants
  (static recovery rate 53%, retries-per-recovery 2.4, avg static recovery time
  61h) rather than fabricated counterfactual data — see `docs/api-mapping.md`.
