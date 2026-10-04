# syntax=docker/dockerfile:1

# python:3.12-slim-bookworm index digest (hub.docker.com, 2026-10-02).
# Pin matches private CI (setup-python 3.12) and requires-python >=3.11.
ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3

# --- Build stage ---
FROM ${PYTHON_IMAGE} AS build
WORKDIR /src

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install runtime deps first (cached when only engine.py changes).
RUN --mount=type=bind,source=pyproject.toml,target=/tmp/pyproject.toml \
    --mount=type=cache,target=/root/.cache/pip \
    python -c "import tomllib, pathlib, subprocess; deps=tomllib.loads(pathlib.Path('/tmp/pyproject.toml').read_text())['project']['dependencies']; subprocess.check_call(['pip','install','--upgrade','pip']); subprocess.check_call(['pip','install','--no-compile',*deps])"

COPY src ./src
COPY pyproject.toml README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps --no-compile .

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
