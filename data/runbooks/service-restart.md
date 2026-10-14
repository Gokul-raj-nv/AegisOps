# Runbook: Service Restart Procedure

**Version:** 1.3
**Owner:** Platform Engineering

## When to Restart

Restart a service only when:
- Memory leak confirmed (RSS growing unboundedly)
- Deadlocked threads that cannot be resolved
- Config change requiring restart (environment variable changes)

**Do not restart** if the root cause is external (DB down, upstream dependency down).

## Restart Procedure

### Rolling restart (preferred — zero downtime)
```bash
kubectl rollout restart deployment/<service-name>
kubectl rollout status deployment/<service-name> --timeout=5m
```

### Verify restart success
```bash
kubectl get pods -l app=<service-name>
# All pods should show Running state
kubectl logs deployment/<service-name> --tail=50
# Should show startup messages, no error floods
```

### Rollback if restart makes things worse
```bash
kubectl rollout undo deployment/<service-name>
```

## Post-Restart Checks

1. Error rate: back to baseline (<0.5%) within 2 minutes
2. Latency: p99 within SLO
3. Health endpoint: returning 200
4. No OOMKilled pods: `kubectl describe pods -l app=<service>`
