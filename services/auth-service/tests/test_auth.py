USER = {"full_name": "Asha Rao", "email": "Asha@Example.com", "password": "supersecret1"}


def signup(client, **overrides):
    return client.post("/api/auth/signup", json={**USER, **overrides})


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200


def test_metrics_exposed(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text


def test_signup_returns_token_and_normalises_email(client):
    resp = signup(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    assert body["user"]["email"] == "asha@example.com"


def test_signup_duplicate_email_rejected(client):
    signup(client)
    resp = signup(client, email="asha@example.com")
    assert resp.status_code == 409


def test_signup_validation(client):
    assert signup(client, password="short").status_code == 422
    assert signup(client, email="not-an-email").status_code == 422


def test_signin_success_and_me(client):
    signup(client)
    resp = client.post("/api/auth/signin", json={"email": "asha@example.com", "password": "supersecret1"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["full_name"] == "Asha Rao"


def test_signin_wrong_password(client):
    signup(client)
    resp = client.post("/api/auth/signin", json={"email": "asha@example.com", "password": "wrongpass1"})
    assert resp.status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_business_metrics(client):
    signup(client)
    client.post("/api/auth/signin", json={"email": "asha@example.com", "password": "wrongpass1"})
    body = client.get("/metrics").text
    assert "quickbook_registered_users 1.0" in body
    assert "quickbook_signups_total" in body
    assert 'quickbook_signins_total{result="failure"}' in body


def test_latency_buckets_cover_slow_requests(client):
    client.get("/health")
    body = client.get("/metrics").text
    assert 'http_request_duration_seconds_bucket{handler="/health",le="10.0"' in body
    assert 'le="0.01"' in body


def test_bcrypt_cost_comes_from_config(client):
    from app.models import User
    from app.db import SessionLocal
    signup(client)
    with SessionLocal() as db:
        assert db.query(User).first().password_hash.startswith("$2b$12$")


def test_load_shedding_rejects_beyond_limit_but_not_probes():
    import anyio
    import httpx
    from app.overload import LoadShedding

    started = []

    async def slow_app(scope, receive, send):
        started.append(scope["path"])
        await anyio.sleep(0.2)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def run():
        mw = LoadShedding(slow_app, limit=2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mw), base_url="http://t") as c:
            results = []

            async def call(path):
                results.append((path, (await c.get(path)).status_code))

            async with anyio.create_task_group() as tg:
                for _ in range(5):
                    tg.start_soon(call, "/api/auth/signin")
                tg.start_soon(call, "/health")
        return results

    results = anyio.run(run)
    work = [s for p, s in results if p != "/health"]
    assert sorted(work) == [200, 200, 503, 503, 503]   # 2 accepted, 3 shed immediately
    assert ("/health", 200) in results                  # probes are never shed
