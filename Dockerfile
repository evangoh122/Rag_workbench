# Stage 1: Build React frontend
FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend

ARG VITE_API_BASE="/api"

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Install Python dependencies
FROM python:3.12-slim AS python-builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 3: Final runtime image
FROM python:3.12-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    nginx \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Add non-root user (UID 1000 for HF Spaces)
RUN useradd -m -u 1000 user
RUN chown -R user:user /app /var/log/nginx /var/lib/nginx /run

# Copy Python packages from builder
COPY --from=python-builder /install /usr/local

# Copy application code
COPY api/ ./api/
COPY scripts/ ./scripts/
COPY main.py run.py ./

# Copy React build from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Copy configuration files
COPY nginx.conf /etc/nginx/nginx.conf
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

RUN mkdir -p /app/data && chown user:user /app/data

EXPOSE 7860

USER user

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
