import logging
from contextlib import asynccontextmanager

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import Counter, Gauge
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import SessionLocal, get_db, init_db
from .logging_config import add_request_logging, setup_logging
from .models import User
from .schemas import AuthResponse, SigninRequest, SignupRequest, UserOut
from .security import create_access_token, decode_access_token, hash_password, verify_password

SERVICE_NAME = "auth-service"
setup_logging(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)
bearer = HTTPBearer(auto_error=False)

# Business metrics for Grafana. Counters only go up; dashboards use rate()/increase() on them.
SIGNUPS = Counter("quickbook_signups_total", "Successful sign-ups")
SIGNINS = Counter("quickbook_signins_total", "Sign-in attempts", ["result"])
for _result in ("success", "failure"):
    SIGNINS.labels(result=_result)  # pre-create series so they show 0 instead of "no data"
REGISTERED_USERS = Gauge("quickbook_registered_users", "Registered users in the database")


def count_users() -> float:
    """Evaluated on every Prometheus scrape (every 30s)."""
    try:
        with SessionLocal() as db:
            return float(db.scalar(select(func.count()).select_from(User)))
    except Exception:
        return float("nan")


REGISTERED_USERS.set_function(count_users)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info("service started")
    yield


app = FastAPI(title="Auth Service", lifespan=lifespan)
add_request_logging(app)
# Exposes /metrics in Prometheus format (request count, latency, etc.).
# Per-endpoint latency histogram. The library default (0.1, 0.5, 1 s) caps p95 at 1 s;
# these buckets keep slow requests measurable under load tests.
LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
Instrumentator().instrument(app, latency_lowr_buckets=LATENCY_BUCKETS).expose(app, include_in_schema=False)


@app.get("/health")
def health():
    """Liveness probe: the process is up."""
    return {"status": "ok"}


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness probe: the service can reach its database."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable")
    return {"status": "ready"}


@app.post("/api/auth/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(full_name=payload.full_name.strip(), email=email, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two signups with the same email at the same moment.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    SIGNUPS.inc()
    logger.info("user signed up", extra={"extra_fields": {"user_id": user.id}})
    return AuthResponse(access_token=create_access_token(user), user=UserOut.model_validate(user))


@app.post("/api/auth/signin", response_model=AuthResponse)
def signin(payload: SigninRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        SIGNINS.labels(result="failure").inc()
        logger.info("failed sign-in attempt")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    SIGNINS.labels(result="success").inc()
    logger.info("user signed in", extra={"extra_fields": {"user_id": user.id}})
    return AuthResponse(access_token=create_access_token(user), user=UserOut.model_validate(user))


@app.get("/api/auth/me", response_model=UserOut)
def me(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = db.get(User, int(claims["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user
