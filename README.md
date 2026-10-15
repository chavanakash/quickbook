# QuickBook – Flight & Train Booking (microservices demo)

A deliberately simple booking app built to practise DevOps: Docker, Kubernetes,
Jenkins CI/CD, Prometheus/Grafana and centralized logging.

User flow: **Sign up / Sign in → choose Flight or Train → search (from, to, date, passengers)
→ passenger details → dummy payment → download ticket PDF**.

## Architecture

```
Browser ──► frontend (React static files on nginx :8080)  ← also the API gateway
              │ /api/auth/*       ──► auth-service       ──► Postgres auth_db
              │ /api/inventory/*  ──► inventory-service  ──► Postgres inventory_db
              │ /api/bookings*    ──► booking-service    ──► Postgres booking_db
              │                                              └─► calls inventory-service (price/trip)
              │ /api/payments     ──► payment-service    ──► Postgres payment_db
              │                                              └─► calls booking-service (fetch + confirm)
              │ /api/tickets/*    ──► ticket-service     (stateless, no DB)
              │                                              └─► calls booking-service, renders PDF
              │ /internal/*       ──► blocked (404) – service-to-service only
```

| Service | Responsibility | Data |
|---|---|---|
| auth-service | sign up, sign in, issue JWT | `users` |
| inventory-service | flight/train schedules, search | `schedules` (seeded on first start) |
| booking-service | create/list bookings, confirm after payment | `bookings` |
| payment-service | dummy card payment | `payments` (only last 4 card digits) |
| ticket-service | PDF e-ticket | none |
| frontend | React UI + nginx gateway | – |

### Key design decisions
- **Database per service** (one Postgres server, separate DB + user per service): services
  never share tables; they talk only through HTTP APIs.
- **PostgreSQL**: bookings and payments are relational and need ACID transactions.
- **Stateless JWT auth**: auth-service signs a token; other services verify it with the shared
  `JWT_SECRET` – no call back to auth-service on each request.
- **Server-side prices**: booking-service gets the price from inventory-service, and payment-service
  gets the amount from booking-service – the browser can't tamper with them.
- **Internal endpoint** `/internal/bookings/{id}/confirm` is protected by `INTERNAL_API_TOKEN`
  and is never routed by the gateway.
- **Every service exposes**: `/health` (liveness), `/ready` (readiness, checks DB),
  `/metrics` (Prometheus), and writes **JSON logs to stdout** (for Loki later).

## Tech stack
- Backend: Python 3.11, FastAPI, SQLAlchemy, PostgreSQL 16, PyJWT, bcrypt, ReportLab
- Frontend: React 18, Vite, React Router; served by nginx (non-root image)
- Tests: pytest (backend, SQLite + mocked HTTP calls), Vitest (frontend), Python smoke test (E2E)

## Repository layout
```
services/<name>/
  app/               FastAPI code
  tests/             pytest unit tests
  Dockerfile         one image per service
  requirements.txt   runtime deps (requirements-dev.txt adds test deps)
frontend/            React app, nginx.conf (gateway), multi-stage Dockerfile
db/init/             SQL that creates the per-service databases/users
scripts/smoke_test.py  end-to-end test through the gateway
docker-compose.yml   whole stack locally
Makefile             shortcuts
```

## Run locally (Docker – recommended)
```bash
docker compose up --build -d       # or: make up
docker compose ps                  # all services should be "healthy"
open http://localhost:3000
python3 scripts/smoke_test.py      # or: make smoke
docker compose logs -f booking-service
docker compose down                # add -v to also wipe the database volume
```

Dummy payment cards: `4111 1111 1111 1111` succeeds, `4000 0000 0000 0002` is declined.
Use any future expiry (MM/YY) and any 3-digit CVV.

Direct service ports (debugging): auth 8001, inventory 8002, booking 8003, payment 8004,
ticket 8005, Postgres 5433. Each service has Swagger docs at `http://localhost:800X/docs`.

## Run tests
```bash
make venv            # one-time: creates .venv with all test deps (needs python3.11)
make test-backend    # pytest for all 5 services
make test-frontend   # vitest
```

## Configuration (environment variables)
| Variable | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | auth, inventory, booking, payment | SQLAlchemy URL (defaults to a local SQLite file) |
| `JWT_SECRET` | auth, booking, payment | sign/verify JWTs – must be identical across them |
| `INTERNAL_API_TOKEN` | booking, payment | protects `/internal/*` |
| `INVENTORY_SERVICE_URL` | booking | e.g. `http://inventory-service:8000` |
| `BOOKING_SERVICE_URL` | payment, ticket | e.g. `http://booking-service:8000` |
| `LOG_LEVEL` | all | default `INFO` |

## Roadmap (DevOps phase)
1. Kubernetes manifests per service (Deployment, Service, ConfigMap, Secret, probes, Ingress)
2. Jenkins pipeline: CI (test → build → scan → push) and CD (deploy → smoke test)
3. Prometheus + Grafana for metrics (`/metrics` is already exposed)
4. Loki + Promtail for logs (JSON logs already on stdout)
