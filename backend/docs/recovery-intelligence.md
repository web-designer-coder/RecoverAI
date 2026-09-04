# RecoverAI Recovery Intelligence — `recoverai-v1`

Phase 4 turns one persisted payment failure into a structured, explainable,
persisted recovery recommendation.

**The AI only recommends. It never executes a recovery, never schedules a
gateway retry and never reads merchant policies** (Phase 5 decides whether a
recommendation is allowed; Phase 6+ would execute). Everything below is a
deterministic function of stored data: no randomness, no network calls, no LLM
in the decision path. The same payment plus the same database history always
produces byte-identical numbers.

---

## Pipeline

```
PaymentFailure ──► FeatureExtractor ──► diagnose ──► score probability ──► confidence
                        ▲                                   │
                        │                                   ▼
IntelligenceRepository (leakage-safe SQL)        recommend action ──► timing windows ──► ERV
                                                                    │
                                                                    ▼
                                          explanation ◄──────── engine.analyze()
                                                                    │
                                                          persist RecoveryDecision
                                                     + AI_DIAGNOSIS / RECOVERY_PREDICTION /
                                                       ACTION_SELECTED audit events
```

All pure logic lives in `app/intelligence/` (independent of FastAPI); all
database access lives in `app/repositories/intelligence_repository.py` and the
service in `app/services/recovery_intelligence_service.py`.

## "Where did the 74% come from?"

Take the seeded payment PAY_82931 (₹8,499 UPI failure, insufficient funds, one
prior attempt) analyzed against the demo merchant's history: it scores
**0.68** recovery probability with **0.88** confidence. Every point of that
number is one of seven documented contributions:

| Signal | Observed value | Contribution |
|---|---|---|
| Base rate | any failure | **+0.35** |
| Failure category | INSUFFICIENT_FUNDS | +0.20 |
| Payment method | UPI | +0.05 |
| Customer history | none recorded for this customer | 0.00 |
| Retry attempt | 1 previous attempt | +0.04 |
| Category recovery rate | only 3 observations — below sample threshold | 0.00 |
| Amount vs history | 0.53× average (<1× band) | +0.04 |

Sum = 0.35 + 0.20 + 0.05 + 0.00 + 0.04 + 0.00 + 0.04 = **0.68**. Note how
missing and under-sampled evidence contributes exactly zero rather than
inflating the score. Each row of that table is also persisted as an entry in
the decision's `signals` JSONB (`name` / `value` / `impact` / `category`) so
any historical decision can be re-derived from its own stored evidence.

Amount bands (`_amount_signal`): <1× average → +0.04 · 1–5× → 0 · >5× → −0.06 ·
no comparison history → 0.

### Category weights

| Category | Signal | Rationale |
|---|---|---|
| INSUFFICIENT_FUNDS | +0.20 | transient — balance/salary cycles resolve it |
| NETWORK_FAILURE | +0.15 | transient connectivity issue |
| INVALID_DETAILS | 0.00 | recoverable but requires customer action |
| EXPIRED_CARD | −0.05 | requires instrument renewal first |
| BANK_DECLINE | −0.25 | issuer semantics may be permanent |
| OTHER | −0.05 | unknown ⇒ slightly conservative |

### Method weights

UPI +0.05 · CARD +0.03 · NET_BANKING +0.02 · WALLET +0.01 · OTHER 0.
(UPI retry UX in India is fastest and least friction.)

### History signals (leakage-safe)

Historical rates come from `IntelligenceRepository`, which counts only
failures with `occurred_at < <current failure's occurred_at>` and excludes the
current payment from its own history. With fewer observations than each
signal's minimum sample size, the contribution is exactly 0 — missing data is
neutral, never fabricated:

- **Customer**: needs ≥3 prior failures; contributes `(rate − 0.5) × 0.20`.
- **Category**: needs ≥5 observations; contributes `(rate − 0.5) × 0.10`.
- **Retry decay**: attempt 0 → +0.08, 1 → +0.04, 2 → −0.06, ≥3 → −0.18.
- **Amount ratio**: current amount ÷ average prior failed amount (None if no history).

### Guardrails

- Result clipped to **[0.01, 0.95]** — certainty either way is never claimed.
- **Hard-decline cap**: provider codes `do_not_honour`, `blocked_by_risk`,
  `fraud_suspected`, `card_reported_lost` (or BANK_DECLINE after ≥3 retries)
  cap probability at **0.15**. A hard decline can never yield a high-probability RETRY.

## Confidence (distinct from probability)

Probability answers *"will this succeed?"*. Confidence answers *"how sure is
the model about that number?"*, driven by evidence quality:

```
0.50 base
+ 0.30 / 0.15 / 0     DataSufficiency HIGH / MEDIUM / LOW
+ (diagnosis_certainty − 0.60) × 0.5      known code 0.90, unknown 0.60, OTHER 0.45
+ 0.05                                    ≥10 prior failures observed
+ 0.04                                    ≥5 observations at this attempt number
+ 0.08 × agreement                        share of signals pointing one way
− 0.05                                    contradictory signals present
clip [0.30, 0.97]
```

**Data sufficiency**: HIGH = ≥20 merchant failures AND ≥5 in-category;
MEDIUM = ≥8 failures and category seen before; LOW otherwise. Sufficiency never
changes the probability itself — only confidence.

## Timing windows

Candidates are fixed: **NOW, +12H, +1D, +2D**. Each window multiplies the base
probability by a per-category domain default (e.g. insufficient funds peaks at
+12H ×1.15 — salary/credit cycles; network failures peak NOW ×1.05). When the
merchant has ≥10 observations for the failure's time-of-day bucket
(morning/afternoon/evening/night, UTC approximation), historical bucket
performance modulates non-NOW windows by at most ±8%.

The winner maximizes **expected recovery value = amount × window probability**
(computed in Decimal, rounded half-up to paise precision). Ties break to the
earliest window. The winning ERV is persisted as
`expected_recovery_amount`, the label as `optimal_window`.

## Action recommender

Deterministic ladder over {RETRY, PAYMENT_UPDATE, CUSTOMER_NOTIFICATION,
ESCALATE, STOP} — evaluated in order:

1. Hard decline → **STOP**
2. BANK_DECLINE: p < 0.20 → **STOP**, else **ESCALATE**
3. EXPIRED_CARD or INVALID_DETAILS → **PAYMENT_UPDATE** (money cannot arrive
   until the instrument changes)
4. p ≥ 0.45 → **RETRY**
5. p ≥ 0.25 → **CUSTOMER_NOTIFICATION**
6. else → **ESCALATE**

The recommender reads no policy tables and checks no retry caps — "AI
recommends, policy decides" is enforced structurally.

## Explanation

A deterministic template renders the final action + strongest supporting
signals into one sentence (e.g. *"RecoverAI recommends a retry because this
customer has a strong history of successful recoveries…"*). An optional LLM
provider exists as a readability layer only: it receives already-final outputs
and structurally cannot change them; on any failure the deterministic text is
used. No chain-of-thought is ever stored.

## Persistence & versioning

Every `POST /api/recoveries/{payment_id}/analyze` appends ONE new
`recovery_decisions` row (model fields: diagnosis, ai_confidence,
recovery_probability, recommended_action, expected_recovery_amount,
optimal_recovery_at, model_version, signals JSONB, explanation, optimal_window,
data_sufficiency). Rows are never updated or deleted. Versioning is explicit:
each row carries a monotonic per-payment `version_number` (1, 2, 3…), and
**the current version is simply the highest `version_number`** — timestamps
alone could tie across transactions, so they are not trusted for ordering.
Re-analyzing therefore builds a decision history for free.

Audit trail per analysis (actor `AI_ENGINE`, category `AI_DECISION`):
`AI_DIAGNOSIS`, `RECOVERY_PREDICTION`, `ACTION_SELECTED`, each carrying
concise metadata (`decision_id`, `model_version`, `probability`, `confidence`,
`action`, `window`, `data_sufficiency`) — never raw payloads.

## API

`POST /api/recoveries/{payment_id}/analyze` → `AnalyzeResponse`
(`decision_id`, `probability`, `confidence`, `recommended_action`,
`optimal_window`, `optimal_recovery_at`, `expected_recovery_value`,
`data_sufficiency`, `signals[]`, `explanation`, `model_version`, `is_current`).

Structured errors: `PAYMENT_NOT_FOUND` (404) · `NO_FAILURE_DATA` (409, no
failure recorded) · `ALREADY_RECOVERED` (409) · `UNSUPPORTED_STATE` (409,
HALTED/AUTHORIZED/PROCESSING).

Internal convention: probability/confidence are floats in **0..1** everywhere
(API, DB, logs). Percent display (74 %) happens only in presentation layers.

## Known limitations

- Weights are hand-set domain priors, not fitted parameters; they are honest
  and auditable, and versioned precisely so they can be replaced by fitted
  models later without invalidating old decisions.
- Time buckets use UTC hours as a proxy for merchant-local time (single-tenant
  demo scope).
- Historical outcome = payment status RECOVERED today; partial outcomes
  (e.g. recovered at lower amount) are not modeled yet.
- The engine analyzes FAILED-family payments only; eligibility errors are
  explicit rather than guessed around.
