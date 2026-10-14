# Payment Service — Architecture Reference

## Purpose
Handles all financial transactions: charge processing, refund issuance, and payment validation.

## Technology
- Python 3.12 / FastAPI
- SQLAlchemy (async) with PostgreSQL
- Stripe SDK for charge processing
- Tenacity for retry logic on Stripe calls

## Endpoints

| Method | Path | Description |
|---|---|---|
| POST | /payments/charge | Process a payment |
| POST | /payments/refund | Issue a refund |
| GET | /payments/{id} | Fetch payment record |
| GET | /payments/health | Health check |

## Database Connection Pool

The service uses SQLAlchemy's `QueuePool` with:
- `pool_size=20` — the number of persistent connections
- `max_overflow=0` — no overflow connections allowed in production
- `pool_timeout=30` — seconds to wait for a connection before raising `TimeoutError`
- `pool_pre_ping=True` — validates connections before use

**Critical:** With `max_overflow=0`, the service can only handle 20 concurrent database operations. At peak load or during slow queries, this pool can become exhausted.

## Known Failure Modes

### 1. DB Connection Pool Exhaustion
**Symptoms:** `TimeoutError: QueuePool limit of size 20 overflow 0 reached`, HTTP 500 errors
**Trigger:** Concurrent requests exceed 20, or long-running transactions hold connections
**Fix:** Increase `DB_POOL_SIZE` or reduce connection hold time
**Runbook:** `runbooks/database-connection-pool.md`

### 2. Stripe API Timeout
**Symptoms:** HTTP 502 on /payments/charge, `stripe.error.Timeout`
**Trigger:** Stripe API degradation (check status.stripe.com)
**Fix:** Retry with exponential backoff; circuit breaker after 5 consecutive failures

### 3. Slow Query Lock Contention
**Symptoms:** Elevated DB latency, connection pool queue growing
**Trigger:** Concurrent UPDATE on same payment record
**Fix:** Add `NOWAIT` to queries; return 409 Conflict instead of blocking

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DB_POOL_SIZE` | 20 | SQLAlchemy pool size |
| `STRIPE_API_KEY` | required | Stripe secret key |
| `STRIPE_TIMEOUT` | 10 | Stripe API timeout in seconds |
| `MAX_RETRY_ATTEMPTS` | 3 | Retry attempts for Stripe calls |
