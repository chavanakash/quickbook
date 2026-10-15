"""JSON logging to stdout.

Containers should log to stdout; a log shipper (Promtail -> Loki) collects it later.
JSON lines are easy for Loki/Grafana to parse and filter (e.g. by service or status).
"""
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(service: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO"))
    # Route uvicorn's own logs through the JSON handler; we log requests ourselves.
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers = []
        uv_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True


# Probe/scrape endpoints are hit every few seconds; logging them is just noise.
QUIET_PATHS = {"/health", "/ready", "/metrics"}


def add_request_logging(app) -> None:
    logger = logging.getLogger("http")

    @app.middleware("http")
    async def log_requests(request, call_next):
        start = time.perf_counter()
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        if request.url.path not in QUIET_PATHS:
            logger.info(
                "request completed",
                extra={
                    "extra_fields": {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                    }
                },
            )
        return response
