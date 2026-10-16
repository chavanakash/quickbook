import os

# Defaults let you run the service alone on a laptop (SQLite file).
# In docker-compose / Kubernetes these are always overridden with env vars.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./auth.db")
JWT_SECRET = os.getenv("JWT_SECRET", "local-dev-jwt-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "120"))

# Overload protection (see app/overload.py). Tuned with the capacity model (capacity-model/).
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))  # each +1 doubles the CPU per login
THREADPOOL_SIZE = int(os.getenv("THREADPOOL_SIZE", "40"))  # concurrent sync handlers (Starlette default 40)
MAX_IN_FLIGHT = int(os.getenv("MAX_IN_FLIGHT", "0"))  # 0 = no load shedding
