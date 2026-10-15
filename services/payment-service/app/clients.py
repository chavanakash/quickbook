"""HTTP calls to booking-service. Kept in one module so tests can mock them easily."""
import httpx

from .config import BOOKING_SERVICE_URL, INTERNAL_API_TOKEN


class BookingNotFound(Exception):
    pass


class UpstreamError(Exception):
    pass


def get_booking(booking_id: int, user_token: str) -> dict:
    """Forward the user's own token, so booking-service enforces ownership."""
    try:
        resp = httpx.get(
            f"{BOOKING_SERVICE_URL}/api/bookings/{booking_id}",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        raise UpstreamError(f"booking-service unreachable: {exc}") from exc

    if resp.status_code == 404:
        raise BookingNotFound()
    if resp.status_code != 200:
        raise UpstreamError(f"booking-service returned {resp.status_code}")
    return resp.json()


def confirm_booking(booking_id: int, payment_ref: str) -> None:
    try:
        resp = httpx.post(
            f"{BOOKING_SERVICE_URL}/internal/bookings/{booking_id}/confirm",
            json={"payment_ref": payment_ref},
            headers={"X-Internal-Token": INTERNAL_API_TOKEN},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        raise UpstreamError(f"booking-service unreachable: {exc}") from exc
    if resp.status_code != 200:
        raise UpstreamError(f"booking confirm returned {resp.status_code}")
