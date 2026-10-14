# Runbook: Database Connection Pool Exhaustion

**Version:** 2.1
**Owner:** Platform Engineering
**Last updated:** 2024-11-15
**Applies to:** payment-service, order-service, auth-service

## Symptoms

- HTTP 500 errors on service endpoints
- Log message: `TimeoutError: QueuePool limit of size N overflow 0 reached`
- Log message: `connection timeout waiting for pool slot`
- DB connection utilization metric at or above 95%
- Increasing request queue depth

## Severity Classification

| Utilization | Severity | Action |
|---|---|---|
| 80–90% | MEDIUM | Monitor; plan for scaling |
| 90–97% | HIGH | Execute this runbook |
| 97–100% | CRITICAL | Immediate action + page on-call |

## Diagnosis Steps

### Step 1: Confirm pool exhaustion
Check the service metrics dashboard:
```
Metric: db_connection_pool_utilization{service="payment-service"}
Expected: <80%
Current: >95% = PROBLEM CONFIRMED
```

### Step 2: Check for long-running transactions
Run on the affected database:
```sql
SELECT pid, now() - query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC
LIMIT 20;
```

### Step 3: Check for lock contention
```sql
SELECT blocked_locks.pid AS blocked_pid,
       blocked_activity.query AS blocked_statement,
       blocking_locks.pid AS blocking_pid
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks
    ON blocking_locks.locktype = blocked_locks.locktype
WHERE NOT blocked_locks.granted;
```

## Remediation

### Option A: Increase pool size (preferred)

1. Update the service environment variable:
   ```
   DB_POOL_SIZE=50  # increase from 20 to 50
   ```
2. Verify the PostgreSQL `max_connections` can accommodate the new pool size.
   - payments_db max_connections = 100
   - With pool_size=50 and 2 replicas: 100 connections used — at limit.
   - **If deploying 2+ replicas:** calculate `pool_size * replicas <= max_connections * 0.9`
3. Rolling restart the service pods:
   ```bash
   kubectl rollout restart deployment/payment-service
   kubectl rollout status deployment/payment-service
   ```
4. Monitor utilization after restart:
   - Target: <70% utilization
   - If still elevated: proceed to Option B

### Option B: Terminate long-running transactions

```sql
-- Terminate queries running longer than 60 seconds
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE query_start < now() - interval '60 seconds'
  AND state != 'idle';
```

### Option C: Emergency restart
Last resort. Only if Options A and B fail.
```bash
kubectl rollout restart deployment/payment-service
```

## Verification

After applying remediation:
1. Check error rate: should drop below 1% within 2 minutes
2. Check pool utilization: should drop below 70%
3. Check latency p99: should return below 2000ms

## Post-Incident

- File a postmortem if this was a P1/P2 incident
- Review max_connections setting for PostgreSQL
- Consider adding PgBouncer for connection multiplexing
- Add alerting at 80% utilization threshold

## Related Incidents

- INC-1521: payment-service pool exhaustion (2024-08-14)
- INC-1842: payment-service pool exhaustion (2024-11-20)
- INC-892: auth-service pool exhaustion (2023-12-01)
