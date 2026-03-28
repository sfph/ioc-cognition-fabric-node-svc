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
# Model quantization stage
# (onnx + curl never reach the runtime image)
# =========================
FROM python:3.11-slim AS model-quantizer

RUN apt-get update && apt-get install -y --no-install-recommends \
  curl \
  ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# onnx is only required by quantize_dynamic; onnxruntime provides the runtime
RUN pip install --no-cache-dir onnxruntime onnx

RUN mkdir -p /tmp/fastembed_cache/ibm-granite/granite-embedding-30m-english && \
  cd /tmp/fastembed_cache/ibm-granite/granite-embedding-30m-english && \
  curl --insecure -L -C - -# -o config.json \
  "https://huggingface.co/ibm-granite/granite-embedding-30m-english/resolve/9b5b096411652ec1189c68fcfb90d0a82c5b45af/config.json" && \
  curl --insecure -L -C - -# -o tokenizer.json \
  "https://huggingface.co/ibm-granite/granite-embedding-30m-english/resolve/9b5b096411652ec1189c68fcfb90d0a82c5b45af/tokenizer.json" && \
  curl --insecure -L -C - -# -o tokenizer_config.json \
  "https://huggingface.co/ibm-granite/granite-embedding-30m-english/resolve/9b5b096411652ec1189c68fcfb90d0a82c5b45af/tokenizer_config.json" && \
  curl --insecure -L -C - -# -o special_tokens_map.json \
  "https://huggingface.co/ibm-granite/granite-embedding-30m-english/resolve/9b5b096411652ec1189c68fcfb90d0a82c5b45af/special_tokens_map.json" && \
  curl --insecure -L -C - -# -o model.onnx \
  "https://huggingface.co/ibm-granite/granite-embedding-30m-english/resolve/9b5b096411652ec1189c68fcfb90d0a82c5b45af/model.onnx"

RUN python - <<'EOF'
from onnxruntime.quantization import quantize_dynamic, QuantType
quantize_dynamic(
    "/tmp/fastembed_cache/ibm-granite/granite-embedding-30m-english/model.onnx",
    "/tmp/fastembed_cache/ibm-granite/granite-embedding-30m-english/model_optimized.onnx",
    weight_type=QuantType.QUInt8,
)
EOF

RUN rm /tmp/fastembed_cache/ibm-granite/granite-embedding-30m-english/model.onnx

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
  EMBEDDING_MODEL_PATH=/tmp/fastembed_cache/ibm-granite/granite-embedding-30m-english \
  HF_HUB_DISABLE_SSL_VERIFY=1 \
  CURL_CA_BUNDLE="" \
  PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# curl removed — model download is handled in model-quantizer stage
RUN apt-get update && apt-get install -y --no-install-recommends \
  ca-certificates \
  libpq5 \
  && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN adduser --disabled-password --gecos "" --uid 1000 app 2>/dev/null || true

COPY --from=builder /opt/venv /opt/venv

# Copy quantized model files only (onnx package stays in model-quantizer stage)
COPY --from=model-quantizer /tmp/fastembed_cache /tmp/fastembed_cache

# Copy app source
COPY src ./src
COPY env.conf ./env.conf
COPY pyproject.toml ./

RUN chown -R 1000:1000 /tmp/fastembed_cache /app

# Switch to non-root user
USER app

EXPOSE 9002

CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "9002"]
