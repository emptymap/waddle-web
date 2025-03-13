# Use an official Python image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

# Install uv
RUN pip install uv

# Create and set the working directory
WORKDIR /app

# Copy the project files
COPY . /app

# Create virtual environment using uv and install dependencies
RUN uv venv && uv pip install -e ".[dev]"

# Default command (override in docker-compose)
CMD ["uv", "run", "src/waddle-api"]
