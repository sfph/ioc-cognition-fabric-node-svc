# ioc-cognition-fabric-node-svc

IoC Cognition Fabric Node Service in Python.

---

## Prerequisites

- Python **3.13+**
- [Poetry](https://python-poetry.org/docs/#installation)
- Docker (optional)

Verify Poetry is installed:

```bash
poetry --version
```

##  Install Dependencies

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
```

## Running the Server

```bash
make run
```

## Running the tests

```bash
make test
```
