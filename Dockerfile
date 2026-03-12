# =========================
# Build stage
# =========================
FROM python:3.13-slim AS builder

ENV POETRY_VERSION=1.8.2 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

COPY pyproject.toml poetry.lock* ./

# Install dependencies (no dev deps)
RUN poetry install --no-interaction --no-ansi --only main


# =========================
# Runtime stage
# =========================
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed deps
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app source
COPY src ./src
COPY env.conf ./env.conf

EXPOSE 9002

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "9002"]
