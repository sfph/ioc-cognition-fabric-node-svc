# ioc-cognition-fabric-node-svc

IoC Cognition Fabric Node Service in Python.

---

## Prerequisites

- Python **3.11+**
- [Poetry](https://python-poetry.org/docs/#installation)
- Docker (optional)
- [IOC Management Plane Service](https://github.com/cisco-eti/ioc-cfn-mgmt-backend-svc) is running and reachable

Verify Poetry is installed:

```bash
poetry --version
```

##  Install Dependencies

**First-time setup:** This project uses internal packages from Cisco Artifactory. See [ARTIFACTORY_INSTALLATION_GUIDE.md](ARTIFACTORY_INSTALLATION_GUIDE.md) for credential setup.

From the repository root:

```bash
make install
```

### Local Development: Download Embedding Models

For local development, download the required embedding models by running:

```bash
./scripts/download_models.sh
```

This script will:
- Download the granite-embedding-30m-english model from HuggingFace
- Quantize the model for optimal performance
- Automatically configure EMBEDDING_MODEL_PATH in env.conf

## Environment Configuration

The service loads environment variables from an `env.conf` file located at the repository root.

Example `env.conf`:

> Notes: following configurations assumes the DB is running [with these configurations](https://github.com/cisco-eti/ioc-cfn-mgmt-backend-svc/blob/clawbee/docker-compose.yml#L8-L33)

```bash
PORT=9002
LOG_LEVEL=INFO
MGMT_URL=http://localhost:9000
CFN_NAME=cfn-local
HEARTBEAT_INTERVAL_SECONDS=29
SERVICE_NAME=ioc-cfn-svc
DB_NAME=ioc-knowledge-db
DB_USER=postgresUser
DB_PASSWORD=postgresPW
DB_HOST=localhost
DB_PORT=5456
LLM_MODEL=azure/gpt-4o # replace with your LLM model
LLM_API_KEY=<your-api-key> # replace with your LLM API key
LLM_BASE_URL=https://<your-resource>.openai.azure.com/ # replace with your Azure OpenAI endpoint
AZURE_API_VERSION=2025-01-01-preview # Azure OpenAI API version
```

## Running the Server

### On local machine
```bash
make run
```

### With Docker

Build with Artifactory credentials:

```bash
docker build \
  --build-arg ARTIFACTORY_USER=YOUR_USERNAME \
  --build-arg ARTIFACTORY_TOKEN=YOUR_TOKEN \
  -t ioc-cfn:test .
```

See [ARTIFACTORY_INSTALLATION_GUIDE.md](ARTIFACTORY_INSTALLATION_GUIDE.md) for setup details.

If IOC Management Plane service is running on Docker, update the env var:
```bash
MGMT_URL=http://host.docker.internal:9000
```

Then run the IOC Cognition Fabric Node image that was built locally:

```bash
docker run \
  -p 9002:9002 \
  --env-file env.conf \
  ioc-cfn:test
```

After running the server, API docs may be accessed at http://localhost:9002/api/docs. Corresponding openapi.json can be found in [docs/openapi.json](./docs/openapi.json).

## Running the tests

```bash
make test
```

## Supported Operations

### [Shared Memory Operations](./docs/shared-memory-operations.md)

### [Semantic Negotiation Example](./docs/negotiation-example.md)
