# syntax=docker/dockerfile:1

# --- Build stage: resolve dependencies with uv from uv.lock -------------------
FROM python:3.12-slim-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project


# --- Runtime stage: same base image, so the venv's interpreter paths match ----
FROM python:3.12-slim-trixie

# tzdata (Europe/Berlin for the nightly preparation) is part of the Debian base image
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 skillbot

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src ./src

# SQLite databases (incl. Microsoft token caches) live in /app/data; mount a volume here
RUN mkdir -p /app/data && chown skillbot:skillbot /app/data
VOLUME ["/app/data"]

USER skillbot

# SIGINT lets asyncio.run cancel tasks and close the Discord connection cleanly on `docker stop`
STOPSIGNAL SIGINT

# main.py loads extensions relative to the working directory (/app)
CMD ["python", "src/main.py"]
