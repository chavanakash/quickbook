import httpx

from .config import BOOKING_SERVICE_URL


class BookingNotFound(Exception):
    pass


class Unauthorized(Exception):
    pass


class UpstreamError(Exception):
    pass


def get_booking(booking_id: int, authorization: str) -> dict:
    """Forward the caller's Authorization header; booking-service checks the token and ownership."""
    try:
        resp = httpx.get(
            f"{BOOKING_SERVICE_URL}/api/bookings/{booking_id}",
            headers={"Authorization": authorization},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        raise UpstreamError(f"booking-service unreachable: {exc}") from exc

    if resp.status_code == 401:
        raise Unauthorized()
    if resp.status_code == 404:
        raise BookingNotFound()
    if resp.status_code != 200:
        raise UpstreamError(f"booking-service returned {resp.status_code}")
    return resp.json()
