from datetime import date, timedelta

TOMORROW = (date.today() + timedelta(days=1)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def search(client, **params):
    query = {"mode": "flight", "origin": "Delhi", "destination": "Mumbai", "date": TOMORROW, **params}
    return client.get("/api/inventory/search", params=query)


def test_health_and_ready(client):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_locations_seeded(client):
    resp = client.get("/api/inventory/locations", params={"mode": "train"})
    assert resp.status_code == 200
    assert "Delhi" in resp.json() and "Chennai" in resp.json()


def test_search_flights_sorted_by_departure(client):
    resp = search(client)
    assert resp.status_code == 200
    trips = resp.json()
    assert len(trips) == 3
    assert all(t["mode"] == "flight" and t["origin"] == "Delhi" for t in trips)
    assert trips[0]["departure_at"] == f"{TOMORROW}T06:15:00"
    assert [t["departure_at"] for t in trips] == sorted(t["departure_at"] for t in trips)


def test_search_is_case_insensitive_and_supports_trains(client):
    resp = search(client, mode="train", origin="delhi", destination="MUMBAI")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_search_validation(client):
    assert search(client, destination="Delhi").status_code == 400
    assert search(client, date=YESTERDAY).status_code == 400
    assert search(client, mode="bus").status_code == 422


def test_get_schedule(client):
    trip = search(client).json()[0]
    resp = client.get(f"/api/inventory/schedules/{trip['schedule_id']}", params={"date": TOMORROW})
    assert resp.status_code == 200
    assert resp.json() == trip
    assert client.get("/api/inventory/schedules/99999", params={"date": TOMORROW}).status_code == 404


def test_seed_is_idempotent(client):
    # Restarting the app must not duplicate the catalog.
    from app.db import SessionLocal
    from app.seed import seed_if_empty

    with SessionLocal() as db:
        seed_if_empty(db)
    assert len(search(client).json()) == 3
