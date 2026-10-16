SERVICES := auth-service inventory-service booking-service payment-service ticket-service
PYTHON ?= python3.11

.PHONY: venv test test-backend test-frontend test-model up down logs smoke clean

venv:
	$(PYTHON) -m venv .venv
	for s in $(SERVICES); do .venv/bin/pip install -q -r services/$$s/requirements-dev.txt; done
	.venv/bin/pip install -q httpx==0.28.1

test: test-backend test-frontend

test-backend:
	for s in $(SERVICES); do (cd services/$$s && ../../.venv/bin/pytest -q) || exit 1; done

test-frontend:
	cd frontend && npm ci && npm test

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

smoke:
	python3 scripts/smoke_test.py http://localhost:3000

clean:
	docker compose down -v

test-model:
	.venv/bin/pytest -q capacity-model/tests
