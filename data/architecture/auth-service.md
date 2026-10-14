# Auth Service — Architecture Reference

## Purpose
Issues and validates JWTs. Manages user sessions and API keys.

## Technology
- Python 3.12 / FastAPI
- PostgreSQL (auth_db) for user records and session tokens
- PyJWT for token signing/verification

## Token TTLs
- Access token: 15 minutes
- Refresh token: 7 days

## Known Failure Modes

### 1. High CPU from Token Validation
**Symptoms:** auth-service CPU >90%, response latency >1s, cascading failures in downstream services
**Trigger:** Sudden spike in requests; bcrypt validation is CPU-intensive
**Fix:** Scale replicas; reduce bcrypt cost factor in non-critical paths

### 2. Database Connection Saturation
**Symptoms:** `could not connect to server` in auth logs
**Trigger:** auth_db pool_size=10 is too small for traffic spike
**Fix:** Increase pool_size; use PgBouncer for connection pooling
