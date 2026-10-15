# Slim base = smaller image, faster pulls, fewer CVEs than the full python image.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Run as a non-root user (Kubernetes security best practice).
RUN useradd --create-home --uid 10001 appuser

# Copy requirements first so the dependency layer is cached when only code changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

USER 10001
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
