# RecoverAI Production Deployment Guide

This document defines the production deployment process, prerequisites, configuration, operational management, and safety protocols for **RecoverAI**.

---

## 1. Deployment Architecture

RecoverAI is architected for a **single-process backend deployment** with a static single-page application (SPA) frontend:

```
┌─────────────────────────────────────────────────────────┐
│                     Reverse Proxy                        │
│                (Nginx / Caddy / Cloudflare)              │
│       TLS termination, HSTS, CORS header enforcement    │
└───────────────┬─────────────────────────┬───────────────┘
                │ /api/*                  │ static assets
                ▼                         ▼
┌───────────────────────────┐ ┌───────────────────────────┐
│     FastAPI Backend       │ │     Frontend SPA          │
│   (Uvicorn single-proc)   │ │  (Vite build output/dist) │
└───────────────┬───────────┘ └───────────────────────────┘
                │ SQL (psycopg3)
                ▼
┌───────────────────────────┐
│   PostgreSQL 14+ Database │
│ (Append-only audit trig)  │
└───────────────────────────┘
```

---

## 2. Prerequisites

### Infrastructure
- **Server**: Linux (Ubuntu 22.04 LTS / Debian 12 / RHEL 9) or Windows Server 2022
- **Python**: 3.12+ with `pip` and `venv`
- **Node.js**: 20+ and `npm` (for building the frontend)
- **PostgreSQL**: 14+ database instance with `psycopg3` compatibility
- **Reverse Proxy**: Nginx, Caddy, or Cloudflare Tunnel with SSL/TLS certificate

---

## 3. Required Environment Variables

Production deployments **MUST** set all of the following environment variables. The application will fail fast at startup if critical secrets are omitted.

### Backend Environment (`backend/.env`)

```ini
# Application Environment (MUST be "production")
APP_ENV=production

# Database Connection (SQLAlchemy format with psycopg driver)
DATABASE_URL=postgresql+psycopg://<user>:<password>@<db-host>:5432/<dbname>

# Server Binding
API_HOST=127.0.0.1
API_PORT=8000

# CORS Allowed Origins (Comma-separated, explicit domains ONLY, NO wildcards)
CORS_ORIGINS=https://app.yourdomain.com,https://yourdomain.com

# Logging Level (INFO | WARNING | ERROR)
LOG_LEVEL=INFO

# HMAC-SHA256 Auth Secret Key (JWT Token Signing)
# Generate: python -c "import secrets; print(secrets.token_hex(32))"
AUTH_SECRET_KEY=e4b7c8d9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7

# Fernet Encryption Key (Credential Storage at Rest)
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
MERCHANT_CREDENTIALS_ENCRYPTION_KEY=gAAAAABl...<32-byte-base64-key>...

# Razorpay TEST MODE Credentials
# (Obtained from Razorpay Dashboard -> Settings -> API Keys in Test Mode)
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Frontend Environment (`.env.local` or environment at build time)

```ini
# Production API Base URL (Must end with /api)
VITE_API_BASE_URL=https://api.yourdomain.com/api
```

---

## 4. Database Setup & Migrations

### A. Fresh Database Setup

1. Create a PostgreSQL database and user:
   ```sql
   CREATE DATABASE recoverai_prod;
   CREATE USER recoverai_user WITH ENCRYPTED PASSWORD 'use_strong_random_password_here';
   GRANT ALL PRIVILEGES ON DATABASE recoverai_prod TO recoverai_user;
   ```

2. Run Alembic migrations to construct the complete schema:
   ```bash
   cd backend
   # Ensure DATABASE_URL is set in environment or backend/.env
   python -m alembic upgrade head
   ```

3. Verify migration status:
   ```bash
   python -m alembic current
   # Should show: ph9_1_auth_password_hash (head)
   ```

### B. Database Migration Rules
- **Migrations are idempotent** and safe to run on deployment.
- **Do NOT run `app.seed` in production.** The seed module is exclusively for local development and testing.
- **Audit trail safety**: The database contains an append-only trigger (`audit_events` table) that raises SQLSTATE `55006` on any `UPDATE` or `DELETE` attempt. Never attempt to truncate or clear `audit_events` directly.

---

## 5. Backend Production Startup

### Startup Command (Single-Process Uvicorn)

Production runs Uvicorn **without** `--reload`.

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

### Systemd Service Setup (`/etc/systemd/system/recoverai-backend.service`)

```ini
[Unit]
Description=RecoverAI FastAPI Backend Service
After=network.target postgresql.service

[Service]
Type=simple
User=recoverai
Group=recoverai
WorkingDirectory=/opt/recoverai/backend
EnvironmentFile=/opt/recoverai/backend/.env
ExecStart=/opt/recoverai/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable recoverai-backend
sudo systemctl start recoverai-backend
```

---

## 6. Frontend Production Build & Deployment

### Build Steps

1. Install dependencies:
   ```bash
   npm ci
   ```

2. Build static production assets with the production API URL:
   ```bash
   VITE_API_BASE_URL=https://api.yourdomain.com/api npm run build
   ```

3. The production bundle is output to `dist/` or `.output/` (depending on router configuration). Serve these static files via Nginx or Caddy.

---

## 7. Reverse Proxy & HTTPS Configuration

### Nginx Production Configuration Example (`/etc/nginx/sites-available/recoverai`)

```nginx
server {
    listen 80;
    server_name app.yourdomain.com api.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security Headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;

    # Backend API Proxy
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 443 ssl http2;
    server_name app.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/app.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.yourdomain.com/privkey.pem;

    root /opt/recoverai/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

---

## 8. Health & Readiness Monitoring

RecoverAI provides two distinct health endpoints for monitoring:

### A. Liveness Probe (`/api/health`)
- **URL**: `GET /api/health`
- **Purpose**: Verifies that the FastAPI process is running.
- **Expected Response**: `200 OK`
  ```json
  {
    "status": "ok",
    "database": "ok",
    "environment": "production"
  }
  ```

### B. Readiness Probe (`/api/ready`)
- **URL**: `GET /api/ready`
- **Purpose**: Verifies database connectivity and production configuration integrity before routing traffic.
- **Expected Response**: `200 OK`
  ```json
  {
    "ready": true,
    "database": "ok",
    "environment": "production",
    "config_issues": null
  }
  ```

---

## 9. Razorpay Production Transition Safety

### Critical Safety Rules

1. **TEST MODE ONLY**: The current codebase is validated against Razorpay **TEST MODE** credentials (`rzp_test_...`). Do NOT switch to live credentials without comprehensive staging validation.
2. **Webhook Secret Isolation**: `RAZORPAY_WEBHOOK_SECRET` is distinct from `RAZORPAY_KEY_SECRET`. Both must be properly configured.
3. **Webhook HMAC Signature Verification**: Signature verification is enforced on raw request bytes via `hmac.compare_digest()`. NEVER bypass signature verification.
4. **Idempotency**: Webhook events are deduplicated via `webhook_events.provider_event_id` unique constraint. Duplicate deliveries safely return `200 OK` with `DUPLICATE_EVENT`.

### Webhook Endpoint Configuration
- **Production Webhook URL**: `https://api.yourdomain.com/api/webhooks/razorpay`
- **Events to subscribe in Razorpay Dashboard**:
  - `payment.failed`
  - `payment.captured`
  - `payment.authorized`

---

## 10. Backup & Recovery Procedure

### A. What to Backup
1. **PostgreSQL Database**: Complete pg_dump including `audit_events`, `payments`, `payment_failures`, `recovery_decisions`, `recovery_actions`, `policies`, and `merchants`.
2. **Environment File**: `/opt/recoverai/backend/.env` (stored securely in password vault).

### B. Daily Automated Backup Command

```bash
pg_dump -U recoverai_user -h localhost -F c -b -v -f "/backups/recoverai_$(date +%Y%m%d_%H%M%S).dump" recoverai_prod
```

### C. Database Restoration Command

```bash
pg_restore -U recoverai_user -h localhost -d recoverai_prod --clean --if-exists "/backups/recoverai_YYYYMMDD_HHMMSS.dump"
```

---

## 11. Production Verification & Smoke Test Checklist

Before opening traffic to merchants, execute this checklist:

- [ ] `APP_ENV=production` set in `backend/.env`
- [ ] `AUTH_SECRET_KEY` set (unique, >= 64 hex chars)
- [ ] `MERCHANT_CREDENTIALS_ENCRYPTION_KEY` set (valid Fernet key)
- [ ] `CORS_ORIGINS` set to exact frontend domain(s)
- [ ] `GET /api/health` returns `200 OK` with `"status": "ok"`
- [ ] `GET /api/ready` returns `200 OK` with `"ready": true`
- [ ] All 236 backend tests pass (`pytest tests/ -q`)
- [ ] TypeScript check clean (`npx tsc --noEmit`)
- [ ] Frontend build succeeds (`npm run build`)
- [ ] Sign Up & Sign In flows verified
- [ ] Dashboard displays KPI metrics
- [ ] Recovery Queue renders list and detail views
- [ ] Policy modification works and bumps policy version
- [ ] Webhook endpoint responds `400` to unsigned requests
