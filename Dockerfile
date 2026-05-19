# Stage 1: Build Vue.js Word add-in
FROM node:22-alpine AS frontend-build
WORKDIR /app

COPY word-plugin/package.json word-plugin/package-lock.json ./
RUN npm ci --legacy-peer-deps

COPY word-plugin/ .
RUN npm run build

# Stage 2: Python backend + nginx serving the built frontend
FROM python:3.12-slim AS final

RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx \
        supervisor \
        curl \
        openssl \
    && rm -rf /var/lib/apt/lists/* \
    && openssl req -x509 -nodes -days 3650 \
         -newkey rsa:2048 \
         -keyout /etc/ssl/private/sprih-selfsigned.key \
         -out /etc/ssl/certs/sprih-selfsigned.crt \
         -subj "/CN=35.237.42.99" \
         -addext "subjectAltName=IP:35.237.42.99"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Skip browser binary download — crawl4ai/playwright binaries are ~300 MB
# and not needed in the cloud image. Set PLAYWRIGHT_BROWSERS_PATH if you
# need browser-based scraping in prod.
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# Install third-party deps first so this layer is cached across code changes
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache \
    && find /app/.venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true

# Copy source and install the project package
COPY backend/ ./backend/
RUN uv sync --frozen --no-dev --no-editable --no-cache

# Serve built Vue SPA via nginx on port 80
COPY --from=frontend-build /app/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/sites-available/default

# supervisord manages nginx + uvicorn in one container
RUN mkdir -p /var/log/supervisor
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 80 443 8000

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
