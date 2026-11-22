# syntax=docker/dockerfile:1

# python:3.12-slim-bookworm index digest (hub.docker.com, 2026-10-02).
# Pin matches private CI (setup-python 3.12) and requires-python >=3.11.
ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
# uv 0.12.13 index digest — keep in sync with setup-uv `version:` in CI (UV_VERSION).
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.13@sha256:b485bd65cc2cf1c9a93b3554012c9c3778cf7b1b5fd3d3096ce9e1226c97e1e6

FROM ${UV_IMAGE} AS uv

# --- Build stage ---
FROM ${PYTHON_IMAGE} AS build
WORKDIR /src
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=0 \
    PATH="/opt/venv/bin:$PATH"

# Locked core deps + pyproject ['optional-dependencies']['docs'] (no ui: check CLI only).
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-editable --extra docs

COPY src ./src
COPY skills ./skills
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --extra docs

# --- Dev stage (Compose live-edit) ---
FROM ${PYTHON_IMAGE} AS dev
WORKDIR /app
RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --ingroup appgroup appuser
COPY --from=build --link --chown=1001:1001 /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
USER appuser
ENTRYPOINT ["skillgate"]
CMD ["check", "/pack"]

# --- Runtime stage ---
FROM ${PYTHON_IMAGE} AS runtime
WORKDIR /app

RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --ingroup appgroup appuser

COPY --from=build --link --chown=1001:1001 /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

USER appuser

LABEL org.opencontainers.image.source=https://github.com/vigneshm1995personal/skillgate
LABEL org.opencontainers.image.title="skillgate"
LABEL org.opencontainers.image.description="Local skill gate CLI: skillgate check /pack"

ENTRYPOINT ["skillgate"]
CMD ["check", "/pack"]