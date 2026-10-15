import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./payment.db")
JWT_SECRET = os.getenv("JWT_SECRET", "local-dev-jwt-secret-change-me")
JWT_ALGORITHM = "HS256"
BOOKING_SERVICE_URL = os.getenv("BOOKING_SERVICE_URL", "http://localhost:8003")
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "local-dev-internal-token")
