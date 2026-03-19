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

```bash
PORT=9002
LOG_LEVEL=INFO
MGMT_URL=http://localhost:9000
CFN_NAME=cfn-local
HEARTBEAT_INTERVAL_SECONDS=29
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
#   "status": "success",
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
#   "status": "success",
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
#  "response_id": "5aec5901-b2f8-40af-af53-b0c3e782d249",
#  "status": "success",
#  "message": "Successfully queried neighbours for:15118c8b99e5813a2239279f0d7fb7c6 in graph:graph_mas_otel.",
#  "records": [
#    {
#      "relationships": [
#        {
#          "id": "5883c6441e793212e18c0f01f46ae8ff",
#          "relation": "ORCHESTRATES_AGENT",
#          "node_ids": [
#            "b9289c4679466c4e15ee79b2dfa55f5a",
#            "15118c8b99e5813a2239279f0d7fb7c6"
#          ],
#          "attributes": {
#            "mas_id": "mas_otel",
#            "source_name": "Miss-Marple",
#            "summarized_context": "Miss-Marple orchestrates the website_selector_agent to identify relevant websites for the query.",
#            "target_name": "website_selector_agent",
#            "wksp_id": "ws1"
#          }
#        },
#        {
#          "id": "7fd39271d0c182b1e849a32db7606522",
#          "relation": "USES_FUNCTION_TO_SEARCH",
#          "node_ids": [
#            "15118c8b99e5813a2239279f0d7fb7c6",
#            "9c3365fe98bfc211d092f9dd4bff9ad4"
#          ],
#          "attributes": {
#            "mas_id": "mas_otel",
#            "source_name": "website_selector_agent",
#            "summarized_context": "The website_selector_agent uses the search_serper function to perform internet searches for relevant websites.",
#            "target_name": "search_serper",
#            "wksp_id": "ws1"
#          }
#        }
#      ],
#      "concepts": [
#        {
#          "id": "b9289c4679466c4e15ee79b2dfa55f5a",
#          "name": "Miss-Marple",
#          "description": "A service that orchestrates various agents to collaboratively answer complex queries by leveraging internet searches, documentation, and reasoning capabilities.",
#          "attributes": {
#            "concept_type": "service",
#            "mas_id": "mas_otel",
#            "wksp_id": "ws1"
#          }
#        },
#        {
#          "id": "9c3365fe98bfc211d092f9dd4bff9ad4",
#          "name": "search_serper",
#          "description": "A function used to search the internet for information on a given topic and return relevant results.",
#          "attributes": {
#            "concept_type": "function",
#            "mas_id": "mas_otel",
#            "wksp_id": "ws1"
#          }
#        }
#      ]
#    }
#  ]
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
#  "response_id": "2b2b0541-a21e-4ec2-8a71-78cbf3bfcd62",
#  "status": "success",
#  "message": "Successfully queried neighbours for:f23a10b39f1b36975ef17b6c3f62a091 in graph:graph_mas_openclaw.",
#  "records": [
#    {
#      "relationships": [
#        {
#          "id": "93fb8f1206eb892276baea1cae8ef8e9",
#          "relation": "ALLOCATES_TO_ENGINEERING_FOR_Q2",
#          "node_ids": [
#            "f23a10b39f1b36975ef17b6c3f62a091",
#            "38aa8a329652f721b4fd719b8b00435e"
#          ],
#          "attributes": {
#            "mas_id": "mas_openclaw",
#            "wksp_id": "ws1",
#            "source_name": "budget-allocation-1772051376",
#            "target_name": "Alex-Engineering",
#            "session_time": "2026-02-25T20:32:58.398Z",
#            "summarized_context": "The budget allocation session involves Alex representing Engineering and requesting $95,000 for infrastructure upgrades, contract engineers, and tooling licenses."                                                                                                                            
#          }
#        },
#        {
#          "id": "cb9f19d5d73dbde2a4fbb60764a825f2",
#          "relation": "ALLOCATES_TO_SALES_FOR_Q2",
#          "node_ids": [
#            "f23a10b39f1b36975ef17b6c3f62a091",
#            "6ccfafb33db135894b23b6402ce1ed25"
#          ],
#          "attributes": {
#            "mas_id": "mas_openclaw",
#            "wksp_id": "ws1",
#            "source_name": "budget-allocation-1772051376",
#            "target_name": "Sam-Sales",
#            "session_time": "2026-02-25T20:32:58.398Z",
#            "summarized_context": "The budget allocation session involves Sam representing Sales and requesting $90,000 for conferences, sales tooling, and demand generation."                                                                                                                                                   
#          }
#        },
#        {
#          "id": "caf3f5cb0a1f7f588a09fc677ab24074",
#          "relation": "ALLOCATES_TO_PRODUCT_FOR_Q2",
#          "node_ids": [
#            "f23a10b39f1b36975ef17b6c3f62a091",
#            "ba0c1701e6d0375bd8739c44dab4b17f"
#          ],
#          "attributes": {
#            "mas_id": "mas_openclaw",
#            "wksp_id": "ws1",
#            "source_name": "budget-allocation-1772051376",
#            "target_name": "Morgan-Product",
#            "session_time": "2026-02-25T20:32:58.398Z",
#            "summarized_context": "The budget allocation session involves Morgan representing Product and requesting $80,000 for user research, UX redesign, and analytics platform."                                                                                                                                             
#          }
#        },
#        {
#          "id": "d1fbaa32108869326a9da391fb4c8b91",
#          "relation": "FOCUSES_ON_OPTIMIZATION",
#          "node_ids": [
#            "7c05d8aeb525d773d9e1113f0e4156f9",
#            "f23a10b39f1b36975ef17b6c3f62a091"
#          ],
#          "attributes": {
#            "mas_id": "mas_openclaw",
#            "wksp_id": "ws1",
#            "source_name": "constraint optimization",
#            "target_name": "budget-allocation-1772051376",
#            "session_time": "2026-02-25T20:32:58.398Z",
#            "summarized_context": "The session focuses on optimizing the allocation of $200,000 across departments, requiring trade-offs and prioritization."
#          }
#        },
#        {
#          "id": "b55074d87529fe0ea55e9b763c2e529a",
#          "relation": "USED_FOR_COMMUNICATION",
#          "node_ids": [
#            "7e3f5537f7662ab256ab31dbac8f4e5d",
#            "f23a10b39f1b36975ef17b6c3f62a091"
#          ],
#          "attributes": {
#            "mas_id": "mas_openclaw",
#            "wksp_id": "ws1",
#            "source_name": "SSTP",
#            "target_name": "budget-allocation-1772051376",
#            "session_time": "2026-02-25T20:32:58.398Z",
#            "summarized_context": "The Structured Semantic Turn Protocol (SSTP) is used for structured communication in the budget allocation session."
#          }
#        }
#      ],
#      "concepts": [
#        {
#          "id": "38aa8a329652f721b4fd719b8b00435e",
#          "name": "Alex-Engineering",
#          "description": "Alex represents the Engineering department, requesting $95,000 for infrastructure upgrades, contract engineers, and tooling licenses.",
#          "attributes": {
#            "mas_id": "mas_openclaw",
#            "wksp_id": "ws1"
#          },
#          "tags": []
#        },
#        {
#          "id": "6ccfafb33db135894b23b6402ce1ed25",
#          "name": "Sam-Sales",
#          "description": "Sam represents the Sales department, requesting $90,000 for conferences, sales tooling, and demand generation.",
#          "attributes": {
#            "mas_id": "mas_openclaw",
#            "wksp_id": "ws1"
#          },
#          "tags": []
#        },
#        {
#          "id": "ba0c1701e6d0375bd8739c44dab4b17f",
#          "name": "Morgan-Product",
#          "description": "Morgan represents the Product department, requesting $80,000 for user research, UX redesign, and analytics platform.",
#          "attributes": {
#            "mas_id": "mas_openclaw",
#            "wksp_id": "ws1"
#          },
#          "tags": []
#        },
#        {
#          "id": "7e3f5537f7662ab256ab31dbac8f4e5d",
#          "name": "SSTP",
#          "description": "Structured Semantic Turn Protocol (SSTP) is used for structured communication in multi-agent sessions, ensuring disciplined and clear exchanges.",                      
#          "attributes": {
#            "mas_id": "mas_openclaw",
#            "wksp_id": "ws1"
#          },
#          "tags": []
#        },
#        {
#          "id": "7c05d8aeb525d773d9e1113f0e4156f9",
#          "name": "constraint optimization",
#          "description": "The session focuses on optimizing the allocation of $200,000 across departments, requiring trade-offs and prioritization.",
#          "attributes": {
#            "mas_id": "mas_openclaw",
#            "wksp_id": "ws1"
#          },
#          "tags": []
#        }
#      ]
#    }
#  ]
#}
```
