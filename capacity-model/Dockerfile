# CI runs `docker build --target test capacity-model`: the model's tests against queueing theory.
FROM python:3.11-slim AS test
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /model
RUN --mount=type=cache,target=/root/.cache/pip pip install simpy==4.1.1 pytest==8.3.4
COPY qbsim ./qbsim
COPY scenarios ./scenarios
COPY tests ./tests
RUN pytest -q tests
