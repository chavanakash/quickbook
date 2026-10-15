import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./booking.db")
JWT_SECRET = os.getenv("JWT_SECRET", "local-dev-jwt-secret-change-me")
JWT_ALGORITHM = "HS256"
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://localhost:8002")
# Shared secret for service-to-service calls (payment-service -> /internal/...).
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "local-dev-internal-token")
