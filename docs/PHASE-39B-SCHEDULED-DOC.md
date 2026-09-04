# Phase 39B-5 — Scheduled Recovery Documentation (Honest)

Date: 2026-09-04
Status: DOCUMENTED / ACCEPTED (no automatic worker invented)

## What exists

- `RecoveryRepository.due_scheduled_actions(merchant_id, now)` (added 39A-1) retrieves `RecoveryAction` rows with `status=SCHEDULED` and `scheduled_at <= now` for the merchant's payments.
- `RecoveryExecutionService.execute()` performs the actual execution when called with an action's idempotency_key.

## What does NOT exist

- No Celery, APScheduler, or persistent job framework in `backend/app/`.
- No external cron/management endpoint that calls `due_scheduled_actions()`.
- `SCHEDULED` actions are persisted in the DB but never execute automatically.

## How production must invoke this

A production deployment needs one of:

1. External job runner (Celery Beat + Worker with persistent store, or APScheduler) that polls `due_scheduled_actions()` periodically.
2. A cron-triggered management endpoint (e.g., `POST /admin/execute-scheduled`) that calls `due_scheduled_actions()` and then `RecoveryExecutionService.execute()` for each result.
3. A manual/admin invocation of `due_scheduled_actions()` followed by execution.

Without this mechanism, scheduled recovery is a persisted state that never transitions to execution.
