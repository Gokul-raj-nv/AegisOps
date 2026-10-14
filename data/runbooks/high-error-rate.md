# Runbook: High HTTP Error Rate

**Version:** 1.0
**Owner:** Platform Engineering

## Triggers

Alert fires when:
- HTTP 5xx rate > 5% over 5 minutes (WARNING)
- HTTP 5xx rate > 15% over 2 minutes (CRITICAL)

## Investigation Steps

### Step 1: Identify scope
```bash
# Check which service is generating errors
kubectl top pods
# Check recent deployments
kubectl rollout history deployment/<service>
```

### Step 2: Check logs
```bash
kubectl logs deployment/<service> --tail=200 | grep -E "ERROR|Exception|500"
```

### Step 3: Check dependencies
- Is the database reachable?
- Is an upstream service down?
- Did a recent deployment go out?

## Common Root Causes and Links

| Error Pattern | Likely Cause | Runbook |
|---|---|---|
| `QueuePool limit` | DB pool exhaustion | database-connection-pool.md |
| `Connection refused` to DB | DB down | database-restart.md |
| `stripe.error.Timeout` | Stripe outage | payment-stripe-outage.md |
| `JWT expired` spike | Auth service overloaded | auth-service-scaling.md |
| After deployment | Regression | rollback.md |
