# Evently

Evently is a self-hostable, event-driven delivery platform for reliably routing events to webhooks and other asynchronous actions, with retries, replay, and full auditability.

It helps backend teams decouple their core services from slow, unreliable, or failure-prone side effects such as third‑party integrations, customer webhooks, and background processing.

---

## Why Evently

Almost every backend system eventually needs to:

* send webhooks to customers
* integrate with third‑party APIs
* trigger background work after a request completes
* retry failed async operations safely
* answer questions like “Did this run?” or “Can we replay it?”

These concerns are often reimplemented repeatedly across services, leading to tight coupling, poor observability, and fragile retry logic.

Evently centralizes this responsibility into a single, reliable, event‑driven system.

---

## What Evently does

1. Your service **emits an event** (e.g. `user.signed_up`)
2. Evently matches **routes** (event → action)
3. Evently creates **jobs** and publishes them to a queue
4. Workers execute the jobs asynchronously
5. All executions are stored with full audit history

Evently is designed to be **local‑first** and **cloud‑optional**.

---

## Architecture (MVP)

```mermaid
flowchart LR
  Producer[Your services] -->|POST /events| API[Evently API]
  API --> PG[(Postgres)]
  API -->|publish job ids| X[jobs.x]
  X --> Q[jobs.webhook.q]
  Q --> W[Evently Worker]
  W -->|POST webhook| Dest[Destination]
  W --> PG

  subgraph RabbitMQ
    X[jobs.x (exchange)]
    Q[jobs.webhook.q]
  end
```

* **Postgres** is the source of truth (events, routes, jobs, attempts)
* **RabbitMQ** provides buffering and back‑pressure
* **Workers** are stateless and horizontally scalable

---

## Local‑first, AWS‑optional

Evently does **not** require an AWS account.

* Local / self‑hosted: Docker Compose
* Cloud deployment (AWS): optional reference configuration (planned)

The core services are cloud‑agnostic and depend only on HTTP, Postgres, RabbitMQ, and environment variables.

---

## Core concepts

* **Event** – a fact that already happened (e.g. `order.paid`)
* **Route** – configuration mapping an event type to an action
* **Action** – what should happen (MVP: `webhook.deliver`)
* **Job** – a concrete execution of an action
* **Attempt** – one execution try of a job (audit trail)

---

## MVP scope

Included:

* Create routes (`POST /routes`)
* Emit events (`POST /events`)
* Create jobs for matching routes
* Publish jobs to RabbitMQ
* Execute webhooks asynchronously
* Persist execution history in Postgres

Planned:

* Retry queues and dead‑letter queues
* Job replay
* Webhook signing (HMAC)
* Guaranteed publish (outbox pattern)
* Metrics and tracing

---

## Quickstart (local)

### Requirements

* Docker
* Docker Compose

### Run

```bash
docker compose up --build
```

### Health check

```bash
curl http://localhost:8080/health
```

RabbitMQ management UI:

* [http://localhost:15672](http://localhost:15672) (guest / guest)

---

## Project goals

Evently prioritizes:

* clarity over abstraction
* correctness over feature count
* reliability and observability
* serving as a real‑world backend reference project

---

## License

MIT
