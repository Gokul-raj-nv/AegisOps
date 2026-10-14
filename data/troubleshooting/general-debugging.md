# General Debugging Guide — ShopFlow

## Principle: Follow the dependency chain

When a service is failing, always check its dependencies first:

```
Order Service failing?
  → Is auth-service healthy? (GET /health)
  → Is orders_db reachable? (psql connection test)
  → Is payment-service healthy? (GET /health)

Payment Service failing?
  → Is payments_db healthy? (check pool utilization)
  → Is Stripe reachable? (check status.stripe.com)
```

## Log Levels

| Level | Meaning |
|---|---|
| DEBUG | Detailed trace (disabled in prod) |
| INFO | Normal operations |
| WARNING | Unexpected but handled (retries, fallbacks) |
| ERROR | Operation failed, returned error to caller |
| CRITICAL | System cannot operate — page immediately |

## Standard Log Fields

All ShopFlow services emit structured JSON logs with:
```json
{
  "timestamp": "2024-11-20T09:14:22Z",
  "level": "ERROR",
  "service": "payment-service",
  "trace_id": "abc123",
  "message": "DB connection timeout",
  "error": "QueuePool limit of size 20 overflow 0 reached"
}
```

## Escalation Contacts

| Team | PagerDuty Rotation | Slack |
|---|---|---|
| Platform | platform-oncall | #platform-oncall |
| Payments | payments-oncall | #payments-team |
| Commerce | commerce-oncall | #commerce-team |
| Security | security-oncall | #security-alerts |
