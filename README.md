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
