FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install Python dependencies (cached layer — rebuilt only when lock file changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Install Chromium + its system deps (playwright fetches them via --with-deps)
RUN uv run playwright install --with-deps chromium

# Copy source and install the project package
COPY backend/ ./backend/
RUN uv sync --frozen --no-dev --no-editable

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
