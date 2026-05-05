# Stage 1: Build Vue.js frontend (wordgpt-main)
FROM node:22-alpine AS frontend-build
WORKDIR /app

COPY wordgpt-main/package.json wordgpt-main/yarn.lock ./
RUN yarn config set network-timeout 300000 \
    && apk add --no-cache g++ make py3-pip \
    && yarn global add node-gyp \
    && yarn install

COPY wordgpt-main/ .
RUN yarn build

# Stage 2: Python backend + nginx serving the Vue frontend
FROM python:3.12-slim AS final

RUN apt-get update && apt-get install -y --no-install-recommends \          
        nginx \
        supervisor \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install third-party dependencies only (skip local package — source not copied yet)
# PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD stops crawl4ai from pulling ~300 MB of browser binaries
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache \
    && find /app/.venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true

# Copy backend source
COPY sandbox-reporting_module/ ./sandbox-reporting_module/

# Serve Vue SPA via nginx on port 80
COPY --from=frontend-build /app/dist /usr/share/nginx/html
RUN printf 'server {\n    listen 80;\n    root /usr/share/nginx/html;\n    index index.html;\n    location /documents/ {\n        proxy_pass http://localhost:8000;\n        proxy_http_version 1.1;\n        proxy_set_header Host $host;\n    }\n    location /threads/ {\n        proxy_pass http://localhost:8000;\n        proxy_http_version 1.1;\n        proxy_set_header Host $host;\n        proxy_buffering off;\n    }\n    location / {\n        try_files $uri $uri/ /index.html;\n    }\n}\n' \
    > /etc/nginx/sites-available/default

# supervisord
RUN mkdir -p /var/log/supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8000 80

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]