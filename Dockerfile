# =========================
# Build stage
# =========================
FROM python:3.11-slim AS builder

ENV POETRY_VERSION=2.1.4 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

COPY pyproject.toml poetry.lock* ./

# Install dependencies (no dev deps)
RUN poetry install --no-interaction --no-ansi --without dev


# =========================
# Runtime stage
# =========================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Create non-root user and group
RUN groupadd --system app && useradd --system --gid app app

# Copy installed deps
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy app source
COPY src ./src
COPY env.conf ./env.conf
COPY pyproject.toml ./

RUN chown -R app:app /app
# Switch to non-root user
USER app

EXPOSE 9002

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "9002"]
