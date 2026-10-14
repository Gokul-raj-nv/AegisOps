# Payment Service Troubleshooting Guide

## Quick Reference: Common Issues

### Issue: HTTP 500 rate > 5%

**Step 1:** Check pool utilization metric
- If > 90%: DB pool exhaustion → see `runbooks/database-connection-pool.md`

**Step 2:** Check Stripe status page (status.stripe.com)
- If Stripe is degraded: Stripe outage — wait or activate circuit breaker

**Step 3:** Check recent deployments
- `kubectl rollout history deployment/payment-service`
- If deployed recently and correlated: rollback

**Step 4:** Check for slow queries
- Connect to payments_db and run `pg_stat_activity` query
- Long-running transactions block pool connections

---

### Issue: Payment requests succeed but are slow (>3s)

**Likely cause:** Stripe API latency elevated
- Check Stripe status page
- Check `stripe_api_latency_p99` metric
- If Stripe p99 > 3s: expected degradation, no fix available — monitor

---

### Issue: Refund endpoint returning 422

**Likely cause:** Invalid refund request (amount > original charge, or already refunded)
- Check application logs for specific validation error
- Verify the payment record status in payments_db

---

## Useful Queries

### Active connections by state
```sql
SELECT state, count(*)
FROM pg_stat_activity
WHERE datname = 'payments_db'
GROUP BY state;
```

### Recent payment errors
```sql
SELECT id, status, error_message, created_at
FROM payments
WHERE status = 'FAILED'
  AND created_at > now() - interval '30 minutes'
ORDER BY created_at DESC
LIMIT 50;
```
