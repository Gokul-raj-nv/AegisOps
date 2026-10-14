# Order Service — Architecture Reference

## Purpose
Manages the full order lifecycle: creation, status tracking, cancellation, and fulfilment.

## Technology
- Python 3.12 / FastAPI
- SQLAlchemy with PostgreSQL (orders_db)
- Synchronous calls to auth-service and payment-service

## Critical Dependency Chain

```
Order Request
    ↓
Auth Service (verify JWT) — if unavailable: 401
    ↓
Inventory check (local DB)
    ↓
Payment Service (charge) — if unavailable: order held
    ↓
Order confirmed → Notification Service queue
```

## Known Failure Modes

### 1. Payment Service Unavailable
**Symptoms:** Orders stuck in PENDING, HTTP 503 on /orders endpoint
**Trigger:** payment-service down or timing out
**Mitigation:** Orders are held in PENDING state with a retry queue (15-minute retry interval)

### 2. Auth Service Timeout
**Symptoms:** All endpoints returning 401 or 503
**Trigger:** auth-service overloaded or down
**Mitigation:** Cached JWT validation for up to 60 seconds

### 3. Database Deadlock
**Symptoms:** `deadlock detected` in logs, elevated error rate
**Trigger:** Concurrent inventory updates on same product
**Fix:** Retry logic with jitter; fixed index ordering on UPDATE statements
