# ShopFlow System Architecture

## Overview
ShopFlow is an e-commerce platform serving ~500k daily active users. The platform processes an average of 12,000 orders per day with peak loads reaching 3x during promotional events.

## Service Inventory

| Service | Language | Replicas (prod) | DB | Owner Team |
|---|---|---|---|---|
| api-gateway | Go | 3 | None | Platform |
| auth-service | Python | 2 | PostgreSQL (auth_db) | Security |
| order-service | Python | 3 | PostgreSQL (orders_db) | Commerce |
| payment-service | Python | 2 | PostgreSQL (payments_db) | Payments |
| notification-service | Node.js | 2 | Redis | Notifications |

## Traffic Flow

```
Customers (HTTPS)
     ↓
API Gateway (rate limiting, SSL termination, routing)
     ↓
┌────┴─────────────────────────────────┐
│              │                       │
Auth Service   Order Service      Payment Service
(JWT verify)   (CRUD, inventory)  (charges, refunds)
                     │                  │
               orders_db           payments_db
                                        │
                                   Stripe API

Notification Service (async)
     ↓
   Redis Queue
     ↓
  Email/SMS Providers
```

## Critical Dependencies

- `order-service` calls `auth-service` for every request (synchronous)
- `order-service` calls `payment-service` synchronously at checkout
- `payment-service` calls Stripe API (external, ~150ms p50 latency)
- `notification-service` consumes Redis queue (async — not in critical path)

## Database Configuration (Production)

| Database | Host | Pool Size | Max Connections | Timeout |
|---|---|---|---|---|
| auth_db | auth-postgres:5432 | 10 | 100 | 30s |
| orders_db | orders-postgres:5432 | 20 | 200 | 30s |
| payments_db | payments-postgres:5432 | 20 | 100 | 30s |

## Known Scaling Limits

- `payment-service` DB pool: 20 connections. At 98% utilization, new requests queue and eventually timeout.
- `notification-service` Redis: if Redis becomes unavailable, notifications are dropped (not retried by default).
- `api-gateway` rate limit: 1000 req/s per upstream service before returning 429.

## SLOs

| Service | Availability | p99 Latency |
|---|---|---|
| api-gateway | 99.9% | 200ms |
| auth-service | 99.9% | 100ms |
| order-service | 99.5% | 500ms |
| payment-service | 99.5% | 2000ms |
| notification-service | 99.0% | N/A (async) |
