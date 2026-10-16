# Development guide

## Run locally with Docker Compose
```bash
docker compose up --build -d       # or: make up
docker compose ps                  # all services "healthy"
open http://localhost:3000
python3 scripts/smoke_test.py      # end-to-end check, or: make smoke
docker compose logs -f booking-service
docker compose down                # add -v to also wipe the database volume
```
Direct service ports (debugging): auth 8001, inventory 8002, booking 8003, payment 8004, ticket 8005,
Postgres 5433. Each service has Swagger docs at `http://localhost:800X/docs`.

Dummy payment cards: `4111 1111 1111 1111` succeeds, `4000 0000 0000 0002` is declined
(any future MM/YY, any 3-digit CVV).

## Tests
```bash
make venv            # one-time: .venv with all test deps (python3.11)
make test-backend    # pytest for all 5 services
make test-frontend   # vitest
docker build --target test services/auth-service   # same tests inside the image (what CI runs)
python3 scripts/smoke_test.py http://quickbook.localhost:8088   # E2E against the cluster
python3 scripts/simulate_users.py http://quickbook.localhost:8088 100 10   # 100 simulated users
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

## Service endpoints
Every Python service: `GET /health` (liveness), `GET /ready` (readiness, checks its DB), `GET /metrics`.

| Service | Public API (via gateway) |
|---|---|
| auth | `POST /api/auth/signup`, `POST /api/auth/signin`, `GET /api/auth/me` |
| inventory | `GET /api/inventory/locations?mode=`, `GET /api/inventory/search?mode=&origin=&destination=&date=`, `GET /api/inventory/schedules/{id}?date=` |
| booking | `POST /api/bookings`, `GET /api/bookings`, `GET /api/bookings/{id}` (+ internal `POST /internal/bookings/{id}/confirm`) |
| payment | `POST /api/payments` |
| ticket | `GET /api/tickets/{booking_id}` → PDF |
