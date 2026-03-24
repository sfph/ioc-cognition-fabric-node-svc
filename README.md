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
AZURE_OPENAI_ENDPOINT=<AZURE_OPENAI_ENDPOINT> # replace with your LLM credentials
AZURE_OPENAI_API_KEY=<AZURE_OPENAI_API_KEY> # replace with your LLM credentials
AZURE_OPENAI_DEPLOYMENT=<AZURE_OPENAI_DEPLOYMENT> # replace with your LLM credentials
AZURE_OPENAI_API_VERSION=<AZURE_OPENAI_API_VERSION> # replace with your LLM credentials
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

## Running the tests

```bash
make test
```

## Shared Memory APIs

After running the server, API docs may be accessed at http://localhost:9002/docs. Corresponding openapi.json can be found in [docs/openapi.json](./docs/openapi.json).

**Create or Update Shared Memories** - Store or update concepts and relationships for inter-agent communication

This API accepts both Otel Trace and Open Claw output.

Example with [Otel Trace](./tests/testdata/otel.json):
```bash
cat tests/testdata/otel.json | jq -s '{
  "header": {
    "agent_id": "agent-1"
  },
  "payload": {
    "metadata": {
      "format": "observe-sdk-otel"
    },
    "data": .[0]
  }
}' | curl -X POST \
  http://localhost:9002/api/workspaces/ws1/multi-agentic-systems/mas_otel/shared-memories \
  -H "Content-Type: application/json" \
  --data-binary @-

# Response (201 Created):
# {
#   "response_id": "9af99ba5-e8aa-47aa-a217-b87dd928ac59",
#   "message": "Successfully saved 10 nodes and 16 edges to graph 'graph_mas_otel'"
# }
```

Example with [OpenClaw output](./tests/testdata/openclaw.json):

```bash
cat tests/testdata/openclaw.json | jq -s '{
  "header": {
    "agent_id": "agent-1",
  },
  "payload": {
    "metadata": {
      "format": "openclaw"
    },
    "data": .[0]
  }
}' | curl -X POST \
  http://localhost:9002/api/workspaces/ws1/multi-agentic-systems/mas_openclaw/shared-memories \
  -H "Content-Type: application/json" \
  --data-binary @-

# Response (201 Created):
# {
#   "response_id": "9af99ba5-e8aa-47aa-a217-b87dd928ac59",
#   "message": "Successfully saved 15 nodes and 17 edges to graph 'graph_mas_openclaw'"
# }
```

**Fetch Shared Memories** - Query stored memories for agent coordination

Query from Otel graph:

```bash
curl -X POST http://localhost:9002/api/workspaces/ws1/multi-agentic-systems/mas_otel/shared-memories/query \
  -H "Content-Type: application/json" \
  -d '{
    "header": {
      "agent_id": "agent-1"
    },
    "search_strategy": "semantic_graph_traversal",
    "intent": "what does the website_selector_agent do?"
  }' | jq

# Response (200 OK):
#{
#  "response_id": "d414f287-aa78-4a79-9e9e-8c7c7226a3eb",
#  "message": "The website_selector_agent performs internet searches using the search_serper function to identify relevant websites."
#}
```

Query from the Openclaw graph:

```bash
curl -X POST http://localhost:9002/api/workspaces/ws1/multi-agentic-systems/mas_openclaw/shared-memories/query \
  -H "Content-Type: application/json" \
  -d '{
    "header": {
      "agent_id": "agent-1"
    },
    "search_strategy": "semantic_graph_traversal",
    "intent": "Tell me something about Q2 budget planning"
  }' | jq

# Response (200 OK):
#{
#  "response_id": "4252795b-70ca-4101-8de5-8a5b944fbe35",
#  "message": "The Q2 budget planning session is constrained by a total budget of $200,000. Alex, the Head of Engineering, is advocating for a $95,000 allocation, while Sam, the Head of Sales, is advocating for a $90,000 allocation."
#}
```
