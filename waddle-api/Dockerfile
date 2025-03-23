FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install build tools + ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libc6-dev \
    python3-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

WORKDIR /app
RUN uv sync --frozen --no-cache

CMD ["uv", "run", "fastapi", "run"]
