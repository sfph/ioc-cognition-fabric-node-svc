# =========================
# Build stage
# =========================
FROM python:3.11-slim AS builder

ENV POETRY_VERSION=2.3.2 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH"

ARG GIT_COMMIT_SHA
ARG GIT_COMMIT_TIME
ARG GIT_BRANCH

WORKDIR /app

# Install system deps (added libpq-dev and build-essential for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 && \
    /root/.local/bin/poetry self add poetry-plugin-export

# Create venv up front
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:/root/.local/bin:$PATH"

COPY pyproject.toml poetry.lock* ./

# Artifactory credentials passed as build args
ARG ARTIFACTORY_USER
ARG ARTIFACTORY_TOKEN

# Install dependencies (no dev deps)
RUN poetry config http-basic.outshift-pypi "$ARTIFACTORY_USER" "$ARTIFACTORY_TOKEN" && \
    poetry export \
      --without dev \
      --without-hashes \
      --format requirements.txt \
      -o /tmp/requirements.txt && \
    PIP_EXTRA_INDEX_URL="https://${ARTIFACTORY_USER}:${ARTIFACTORY_TOKEN}@artifactory.devhub-cloud.cisco.com/artifactory/api/pypi/outshift-pypi/simple" \
    /opt/venv/bin/pip install --no-input -r /tmp/requirements.txt


# =========================
# Runtime stage
# =========================
FROM python:3.11-slim

# Build-time git metadata
ARG GIT_COMMIT_SHA=unknown
ARG GIT_COMMIT_TIME=unknown
ARG GIT_BRANCH=unknown

ENV GIT_COMMIT_SHA=${GIT_COMMIT_SHA} \
    GIT_COMMIT_TIME=${GIT_COMMIT_TIME} \
    GIT_BRANCH=${GIT_BRANCH} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EMBEDDING_MODEL_PATH=/tmp/fastembed_cache/Qdrant/bge-small-en-v1.5-onnx-Q \
    HF_HUB_DISABLE_SSL_VERIFY=1 \
    CURL_CA_BUNDLE="" \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN adduser --disabled-password --gecos "" --uid 1000 app 2>/dev/null || true

COPY --from=builder /opt/venv /opt/venv

# Copy app source
COPY src ./src
COPY env.conf ./env.conf
COPY pyproject.toml ./

# Pre-download fastembed model files directly from HuggingFace
# Using curl with --insecure to bypass SSL certificate issues
RUN mkdir -p /tmp/fastembed_cache/Qdrant/bge-small-en-v1.5-onnx-Q && \
    cd /tmp/fastembed_cache/Qdrant/bge-small-en-v1.5-onnx-Q && \
    curl --insecure -L -C - -# -o model_optimized.onnx \
      "https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/resolve/52398278842ec682c6f32300af41344b1c0b0bb2/model_optimized.onnx" && \
    curl --insecure -L -C - -# -o tokenizer.json \
      "https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/resolve/52398278842ec682c6f32300af41344b1c0b0bb2/tokenizer.json" && \
    curl --insecure -L -C - -# -o tokenizer_config.json \
      "https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/resolve/52398278842ec682c6f32300af41344b1c0b0bb2/tokenizer_config.json" && \
    curl --insecure -L -C - -# -o special_tokens_map.json \
      "https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/resolve/52398278842ec682c6f32300af41344b1c0b0bb2/special_tokens_map.json" && \
    curl --insecure -L -C - -# -o config.json \
      "https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/resolve/52398278842ec682c6f32300af41344b1c0b0bb2/config.json" && \
    curl --insecure -L -C - -# -o vocab.txt \
      "https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/resolve/52398278842ec682c6f32300af41344b1c0b0bb2/vocab.txt" && \
    chown -R 1000:1000 /tmp/fastembed_cache /app

# Switch to non-root user
USER app

EXPOSE 9002

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "9002"]
