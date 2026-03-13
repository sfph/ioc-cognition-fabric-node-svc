# Artifactory Installation Guide

Quick guide for developers to install dependencies from Cisco Artifactory.

---

## Step 1: Get Your Credentials

1. Go to https://artifactory.devhub-cloud.cisco.com
2. Login → Profile → Edit Profile → Generate API Token
3. Save your **username** and **token**

---

## Step 2: Configure Poetry

Run this command with your credentials:

```bash
poetry config http-basic.outshift-pypi YOUR_USERNAME YOUR_TOKEN
```

Example:
```bash
poetry config http-basic.outshift-pypi user123 abc123XYZ456token789
```

If you have issues, disable keyring:
```bash
poetry config keyring.enabled false
```

---

## Step 3: Install Dependencies

```bash
poetry install
```

---

## Step 4: Test Installation

```bash
poetry run python -c "import knowledge_memory; print(f'✓ knowledge-memory v{knowledge_memory.__version__}')"
```

---

## Usage Example

```python
from knowledge_memory import (
    query_knowledge_graph,
    upsert_knowledge_graph,
    query_vector_store,
    upsert_vector_store
)

# Query knowledge graph
results = query_knowledge_graph(query="your query")

# Upsert vector store
upsert_vector_store(data={"your": "data"})
```

---

## Troubleshooting

### Authorization Error

If you get "Authorization error accessing...", verify your credentials:

```bash
curl -s -u "YOUR_USERNAME:YOUR_TOKEN" \
  https://artifactory.devhub-cloud.cisco.com/artifactory/api/pypi/outshift-pypi/simple/knowledge-memory/
```

If this fails, regenerate your token in Artifactory and reconfigure Poetry (Step 2).

---

## Docker Build

To build the Docker image locally, pass your Artifactory credentials as build args:

```bash
docker build \
  --build-arg ARTIFACTORY_USER=YOUR_USERNAME \
  --build-arg ARTIFACTORY_TOKEN=YOUR_TOKEN \
  -t your-image-name .
```

Example:
```bash
docker build \
  --build-arg ARTIFACTORY_USER=user123 \
  --build-arg ARTIFACTORY_TOKEN=abc123XYZ456token789 \
  -t ioc-cognition-fabric-node-svc:local .
```

---

## CI/CD Setup

The CI workflow automatically retrieves Artifactory credentials from Vault and passes them to Docker build. No manual configuration needed - credentials are managed centrally via Vault.

---

## Security

- Never commit tokens to Git
- Each developer needs their own token
- Credentials stored in `~/.config/pypoetry/auth.toml`
- Docker build args are not persisted in image layers
