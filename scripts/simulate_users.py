#!/usr/bin/env python3
"""Simulates realistic users booking flights/trains, to generate traffic for Grafana.

Each user: sign up (sometimes mistypes the password once), searches 1-3 times, usually books
1-4 passengers, pays (some cards are declined, some users give up) and downloads the ticket.

Standard library only.
Usage: python3 scripts/simulate_users.py [BASE_URL] [USERS] [CONCURRENCY]
       python3 scripts/simulate_users.py http://localhost:3000 100 10
"""
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Lock

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000").rstrip("/")
USERS = int(sys.argv[2]) if len(sys.argv) > 2 else 100
CONCURRENCY = int(sys.argv[3]) if len(sys.argv) > 3 else 10


def resolve_localhost(url):
    """Browsers treat *.localhost as this machine, but macOS doesn't (without /etc/hosts).
    Connect to 127.0.0.1 and send the original name as the Host header so the ingress still routes."""
    parts = urllib.parse.urlsplit(url)
    if parts.hostname and parts.hostname.endswith(".localhost"):
        netloc = "127.0.0.1" + (f":{parts.port}" if parts.port else "")
        return urllib.parse.urlunsplit(parts._replace(netloc=netloc)), parts.netloc
    return url, None


BASE_URL, HOST_HEADER = resolve_localhost(BASE_URL)

FIRST = ["Aarav", "Vivaan", "Aditya", "Arjun", "Sai", "Ishaan", "Rohan", "Kabir", "Ananya", "Diya",
         "Priya", "Isha", "Meera", "Kavya", "Saanvi", "Riya", "Neha", "Akash", "Rahul", "Sneha"]
LAST = ["Sharma", "Verma", "Reddy", "Iyer", "Nair", "Patel", "Gupta", "Rao", "Singh", "Das",
        "Mehta", "Joshi", "Kulkarni", "Chavan", "Menon", "Bose"]
GOOD_CARD, DECLINED_CARD = "4111111111111111", "4000000000000002"

stats, lock = Counter(), Lock()


def count(key, n=1):
    with lock:
        stats[key] += n


def call(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if HOST_HEADER:
        headers["Host"] = HOST_HEADER
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE_URL + path, method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw, ctype = resp.read(), resp.headers.get("Content-Type", "")
            return resp.status, (json.loads(raw) if "json" in ctype else raw)
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def random_name():
    return f"{random.choice(FIRST)} {random.choice(LAST)}"


def simulate(n, cities):
    rng = random.Random()
    name = random_name()
    email = f"{name.lower().replace(' ', '.')}.{int(time.time() * 1000) % 10**8}{n}@example.com"
    password = f"pass{rng.randint(10**5, 10**6)}"

    status, auth = call("POST", "/api/auth/signup", {"full_name": name, "email": email, "password": password})
    if status != 201:
        count(f"errors: signup (HTTP {status})")
        return
    count("users signed up")

    if rng.random() < 0.08:  # mistyped password once
        call("POST", "/api/auth/signin", {"email": email, "password": password + "x"})
        count("failed sign-ins (typo)")
    status, auth = call("POST", "/api/auth/signin", {"email": email, "password": password})
    token = auth["access_token"]

    mode = rng.choice(["flight", "train"])
    trips, travel_date = [], None
    for _ in range(rng.randint(1, 3)):
        origin, destination = rng.sample(cities[mode], 2)
        travel_date = (date.today() + timedelta(days=rng.randint(1, 60))).isoformat()
        query = urllib.parse.urlencode({"mode": mode, "origin": origin, "destination": destination, "date": travel_date})
        status, trips = call("GET", f"/api/inventory/search?{query}")
        count(f"searches ({mode})")
        time.sleep(rng.uniform(0.05, 0.3))  # "thinking" time

    if not trips or rng.random() < 0.15:
        count("browsed only (no booking)")
        return

    trip = rng.choice(trips)
    passengers = [{"name": name if i == 0 else random_name(), "age": rng.randint(3, 75)}
                  for i in range(rng.randint(1, 4))]
    status, booking = call("POST", "/api/bookings",
                           {"schedule_id": trip["schedule_id"], "travel_date": travel_date, "passengers": passengers},
                           token=token)
    if status != 201:
        count(f"errors: booking (HTTP {status})")
        return
    count(f"bookings created ({mode})")

    card = {"booking_id": booking["id"], "card_holder": name, "cvv": f"{rng.randint(100, 999)}",
            "expiry": f"{rng.randint(1, 12):02d}/{(date.today().year + rng.randint(1, 4)) % 100:02d}"}
    if rng.random() < 0.10:
        call("POST", "/api/payments", {**card, "card_number": DECLINED_CARD}, token=token)
        count("payments declined")
        if rng.random() < 0.4:
            count("abandoned after decline")
            return
    status, payment = call("POST", "/api/payments", {**card, "card_number": GOOD_CARD}, token=token)
    if status != 201:
        count(f"errors: payment (HTTP {status})")
        return
    count("bookings paid")
    count("revenue INR", int(payment["amount"]))

    status, pdf = call("GET", f"/api/tickets/{booking['id']}", token=token)
    if status == 200 and pdf[:4] == b"%PDF":
        count("tickets downloaded")
    else:
        count(f"errors: ticket (HTTP {status})")


def main():
    cities = {m: call("GET", f"/api/inventory/locations?mode={m}")[1] for m in ("flight", "train")}
    print(f"Simulating {USERS} users against {BASE_URL} ({CONCURRENCY} at a time)...")
    started = time.time()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        for future in [pool.submit(simulate, n, cities) for n in range(USERS)]:
            try:
                future.result()
            except Exception as exc:  # keep going; report at the end
                count(f"errors: {type(exc).__name__}")
    print(f"Done in {time.time() - started:.1f}s\n")
    for key in sorted(stats):
        value = f"₹{stats[key]:,}" if key == "revenue INR" else stats[key]
        print(f"  {key:28} {value}")


if __name__ == "__main__":
    main()
