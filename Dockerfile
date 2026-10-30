# Stage 1: Install Python dependencies with uv
FROM python:3.11-slim AS python-builder

# Official uv binary — pinned so image builds are reproducible.
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/

WORKDIR /app

# Debian package versions are not pinned because the snapshot mirrors rotate;
# the base image tag plus uv.lock pinning of the Python tree is the
# reproducibility control here (DL3008 waived inline below).
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install into a dedicated venv, byte-compiled and copied (no hardlinks) so the
# venv can be copied into the final stage. UV_PYTHON_DOWNLOADS=never keeps uv on
# the image interpreter instead of fetching its own Python.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.11

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Stage 2: Final runtime image
FROM python:3.11-slim AS runtime

WORKDIR /app

# Same DL3008 waiver as the builder stage above.
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Add non-root user (UID 1000 for HF Spaces)
RUN useradd -m -u 1000 user \
    && chown -R user:user /app

# Copy the uv-managed virtualenv from the builder
COPY --from=python-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY api/ ./api/
COPY scripts/ ./scripts/
COPY data/sentiment_dict/ ./data/sentiment_dict/
COPY main.py run.py ./

RUN mkdir -p /app/data && chown -R user:user /app/data

EXPOSE 7860

USER user

# Restore the prebuilt DuckDB (Qwen embeddings + XBRL + graph_triples) from the
# HF dataset BEFORE uvicorn opens the DB connection. Falls through (|| true) to
# the startup seed if the fetch fails (no token / network / repo missing).
# Then restore the runtime/review DB (audit log, HITL decisions, eval results)
# from its Parquet snapshots in the same dataset — the Space has no persistent
# volume, so this is how that data survives restarts.
#
# seed_on_startup.py backgrounds itself (&) — it polls /api/health on 127.0.0.1
# and does its real work (XBRL refresh / embedding) only once uvicorn is up,
# same as when supervisord ran it alongside uvicorn. uvicorn itself is the
# foreground process now (exec, no supervisord) and binds the Space's public
# port directly — there's no nginx in front of it anymore (the frontend moved
# to evangoh-frontend, which serves the portfolio + RAG Workbench UI directly).
#
# The CMD runs bare `python`/`uvicorn` on purpose: PATH points at the copied
# /opt/venv created by `uv sync`, so it is the locked environment, not a
# system interpreter.
CMD ["sh", "-c", "cd /app && PYTHONPATH=/app python -m scripts.fetch_db_from_dataset || true; PYTHONPATH=/app python -m scripts.restore_review_db || true; python scripts/seed_on_startup.py & exec uvicorn api.main:app --host 0.0.0.0 --port 7860"]
# build: v7 — backend-only (frontend moved to evangoh-frontend); uv (pyproject.toml + uv.lock)
