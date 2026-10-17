# Stage 1: Install Python dependencies
FROM python:3.11-slim AS python-builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.11-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Add non-root user (UID 1000 for HF Spaces)
RUN useradd -m -u 1000 user
RUN chown -R user:user /app

# Copy Python packages from builder
COPY --from=python-builder /install /usr/local

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
CMD ["sh", "-c", "cd /app && PYTHONPATH=/app python -m scripts.fetch_db_from_dataset || true; PYTHONPATH=/app python -m scripts.restore_review_db || true; python scripts/seed_on_startup.py & exec uvicorn api.main:app --host 0.0.0.0 --port 7860"]
# build: v7 — backend-only (frontend moved to evangoh-frontend); uvicorn serves 7860 directly, no nginx/supervisord
