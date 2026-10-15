"""HTTP calls to other services. Kept in one module so tests can mock them easily."""
from datetime import date

import httpx

from .config import INVENTORY_SERVICE_URL


class TripNotAvailable(Exception):
    pass


class UpstreamError(Exception):
    pass


def get_trip(schedule_id: int, travel_date: date) -> dict:
    try:
        resp = httpx.get(
            f"{INVENTORY_SERVICE_URL}/api/inventory/schedules/{schedule_id}",
            params={"date": travel_date.isoformat()},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        raise UpstreamError(f"inventory-service unreachable: {exc}") from exc

    if resp.status_code in (400, 404, 422):
        raise TripNotAvailable(resp.json().get("detail", "Trip not available"))
    if resp.status_code != 200:
        raise UpstreamError(f"inventory-service returned {resp.status_code}")
    return resp.json()
