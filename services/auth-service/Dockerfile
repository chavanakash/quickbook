# Multi-stage build:
#   builder -> installs dependencies into a virtualenv (/opt/venv)
#   test    -> builder + test tools + tests; CI runs `docker build --target test`
#   runtime -> fresh Alpine base + only the virtualenv and app code (default target)

# ---- builder ----
FROM python:3.11-alpine AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
# BuildKit cache mount: pip's download cache is reused across builds but never stored in the image.
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

# ---- test ----
FROM builder AS test
COPY requirements-dev.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements-dev.txt
COPY pytest.ini .
COPY app ./app
COPY tests ./tests
RUN pytest -q

# ---- runtime ----
FROM python:3.11-alpine AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Run as a non-root user (Kubernetes security best practice).
RUN adduser -D -u 10001 appuser
WORKDIR /app

# Only the installed packages come across - no pip cache, no build leftovers, no tests.
COPY --from=builder /opt/venv /opt/venv
COPY app ./app

USER 10001
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
