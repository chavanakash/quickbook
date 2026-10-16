#!/usr/bin/env python3
"""End-to-end smoke test through the gateway: signup -> search -> book -> pay -> PDF.

Standard library only, so it runs on any CI agent with Python 3.
Usage: python3 scripts/smoke_test.py [BASE_URL]   (default http://localhost:3000)
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000").rstrip("/")


def resolve_localhost(url):
    """Browsers treat *.localhost as this machine, but macOS doesn't (without /etc/hosts).
    Connect to 127.0.0.1 and send the original name as the Host header so the ingress still routes."""
    parts = urllib.parse.urlsplit(url)
    if parts.hostname and parts.hostname.endswith(".localhost"):
        netloc = "127.0.0.1" + (f":{parts.port}" if parts.port else "")
        return urllib.parse.urlunsplit(parts._replace(netloc=netloc)), parts.netloc
    return url, None


BASE_URL, HOST_HEADER = resolve_localhost(BASE_URL)


def call(method, path, body=None, token=None, expect=200):
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if HOST_HEADER:
        headers["Host"] = HOST_HEADER
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status, raw, ctype = resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as err:
        status, raw, ctype = err.code, err.read(), err.headers.get("Content-Type", "")
    if status != expect:
        raise AssertionError(f"{method} {path}: expected {expect}, got {status}: {raw[:300]!r}")
    return json.loads(raw) if "json" in ctype else raw


def step(name, fn):
    fn_result = fn()
    print(f"  PASS  {name}")
    return fn_result


def main():
    print(f"Smoke testing {BASE_URL}")
    email = f"smoke-{int(time.time())}@example.com"
    travel_date = (date.today() + timedelta(days=7)).isoformat()

    step("frontend serves index.html", lambda: call("GET", "/"))
    auth = step(
        "sign up",
        lambda: call("POST", "/api/auth/signup", {"full_name": "Smoke Test", "email": email, "password": "smoketest123"}, expect=201),
    )
    token = step(
        "sign in",
        lambda: call("POST", "/api/auth/signin", {"email": email, "password": "smoketest123"}),
    )["access_token"]
    assert auth["user"]["email"] == email

    trips = step(
        "search trains",
        lambda: call("GET", f"/api/inventory/search?mode=train&origin=Delhi&destination=Mumbai&date={travel_date}"),
    )
    assert trips, "no trips returned"

    booking = step(
        "create booking",
        lambda: call(
            "POST",
            "/api/bookings",
            {"schedule_id": trips[0]["schedule_id"], "travel_date": travel_date, "passengers": [{"name": "Smoke Test", "age": 30}]},
            token=token,
            expect=201,
        ),
    )
    assert booking["status"] == "PENDING_PAYMENT"

    step("ticket blocked before payment", lambda: call("GET", f"/api/tickets/{booking['id']}", token=token, expect=409))

    card = {"booking_id": booking["id"], "card_holder": "Smoke Test", "expiry": f"12/{(date.today().year + 2) % 100:02d}", "cvv": "123"}
    step("declined card rejected", lambda: call("POST", "/api/payments", {**card, "card_number": "4000000000000002"}, token=token, expect=402))
    step("payment succeeds", lambda: call("POST", "/api/payments", {**card, "card_number": "4111111111111111"}, token=token, expect=201))

    confirmed = step("booking confirmed", lambda: call("GET", f"/api/bookings/{booking['id']}", token=token))
    assert confirmed["status"] == "CONFIRMED", confirmed

    pdf = step("ticket PDF downloads", lambda: call("GET", f"/api/tickets/{booking['id']}", token=token))
    assert pdf.startswith(b"%PDF"), "response is not a PDF"

    step("internal endpoint not exposed via gateway", lambda: call("POST", f"/internal/bookings/{booking['id']}/confirm", {"payment_ref": "x"}, expect=404))
    print("All smoke tests passed")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"  FAIL  {exc}")
        sys.exit(1)
