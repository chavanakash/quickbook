"""Overload protection: bounded concurrency with fast rejection (load shedding).

Without it, an overloaded pod accepts everything, shares its CPU between all of it, and every
request ends in a 30 s timeout. With it, requests beyond `limit` get an immediate 503 + Retry-After,
and the ones accepted finish quickly. Probe and metrics paths are exempt: a busy pod is not a broken
pod, and must keep answering Kubernetes.
"""
from prometheus_client import Counter, Gauge

EXEMPT_PATHS = {"/health", "/ready", "/metrics"}
SHED = Counter("quickbook_requests_shed_total", "Requests rejected by load shedding (503)")
IN_FLIGHT = Gauge("quickbook_requests_in_flight", "Requests being handled, excluding probes")
BUSY_BODY = b'{"detail":"Server busy, please retry"}'


class LoadShedding:
    """Pure ASGI middleware. Runs on the single event loop, so a plain counter is safe."""

    def __init__(self, app, limit: int):
        self.app, self.limit, self.in_flight = app, limit, 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.limit <= 0 or scope["path"] in EXEMPT_PATHS:
            return await self.app(scope, receive, send)
        if self.in_flight >= self.limit:
            SHED.inc()
            await send({"type": "http.response.start", "status": 503,
                        "headers": [(b"content-type", b"application/json"), (b"retry-after", b"2"),
                                    (b"content-length", str(len(BUSY_BODY)).encode())]})
            await send({"type": "http.response.body", "body": BUSY_BODY})
            return
        self.in_flight += 1
        IN_FLIGHT.set(self.in_flight)
        try:
            await self.app(scope, receive, send)
        finally:
            self.in_flight -= 1
            IN_FLIGHT.set(self.in_flight)
