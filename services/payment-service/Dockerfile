# ---- base: runtime dependencies, shared by the test and runtime stages ----
# Slim base = smaller image, faster pulls, fewer CVEs than the full python image.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy requirements first so the dependency layer is cached when only code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- test: CI runs `docker build --target test` - the build fails if any test fails ----
FROM base AS test
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY pytest.ini .
COPY app ./app
COPY tests ./tests
RUN pytest -q

# ---- runtime (default target): only app code, no tests or test tools ----
FROM base AS runtime

# Run as a non-root user (Kubernetes security best practice).
RUN useradd --create-home --uid 10001 appuser

COPY app ./app

USER 10001
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
