import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["INTERNAL_API_TOKEN"] = "test-internal-token"

from datetime import date, datetime, timedelta, timezone  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import clients  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

TRAVEL_DATE = date.today() + timedelta(days=3)


def auth_header(user_id: int = 1, email: str = "asha@example.com") -> dict:
    token = jwt.encode(
        {"sub": str(user_id), "email": email, "name": "Asha", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def fake_trip(schedule_id: int, travel_date: date) -> dict:
    if schedule_id == 404:
        raise clients.TripNotAvailable("Schedule not found")
    return {
        "schedule_id": schedule_id,
        "mode": "flight",
        "code": "SJ-1000",
        "operator": "SkyJet",
        "origin": "Delhi",
        "destination": "Mumbai",
        "departure_at": f"{travel_date.isoformat()}T06:15:00",
        "arrival_at": f"{travel_date.isoformat()}T08:42:00",
        "duration_minutes": 147,
        "price": 6140.0,
    }


@pytest.fixture()
def client(monkeypatch):
    # Replace the real HTTP call to inventory-service with a fake (unit test isolation).
    monkeypatch.setattr(clients, "get_trip", fake_trip)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
