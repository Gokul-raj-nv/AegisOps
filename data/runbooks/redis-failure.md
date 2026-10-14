# Runbook: Redis Failure (Notification Service)

**Version:** 1.1
**Owner:** Notifications Team

## Impact

If Redis is unavailable:
- Email/SMS notifications are not sent
- Orders complete successfully (notifications are async, not in critical path)
- Notifications published while Redis is down are LOST (no persistent queue fallback)

## Symptoms

- `notification-service` log: `redis.exceptions.ConnectionError`
- Spike in notification delivery failure metric
- Users report not receiving order confirmations

## Remediation

### Step 1: Confirm Redis is down
```bash
redis-cli -h redis-host ping
# Expected: PONG
# If no response: Redis is down
```

### Step 2: Restart Redis
```bash
kubectl rollout restart deployment/redis
kubectl rollout status deployment/redis
```

### Step 3: Verify notification-service reconnects
```bash
kubectl logs deployment/notification-service --tail=50 | grep redis
```

### Step 4: Handle missed notifications
- Check order-service for orders in PENDING_NOTIFICATION state
- Manually trigger notification requeue if needed (contact Notifications team)

## Prevention

- Add Redis Sentinel for high availability
- Implement persistent queue fallback (e.g., SQS) for critical notifications
