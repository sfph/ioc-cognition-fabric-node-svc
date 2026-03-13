import os
import tomllib


def get_repo_root() -> str:
    """Get the repository root path by locating pyproject.toml.

    Returns:
        str: Absolute path to the repository root

    Raises:
        RuntimeError: If pyproject.toml is not found in the directory tree
    """
    current = os.path.dirname(os.path.abspath(__file__))
    while current != os.path.dirname(current):  # Stop at filesystem root
        if os.path.exists(os.path.join(current, "pyproject.toml")):
            return current
        current = os.path.dirname(current)
    raise RuntimeError("Could not find repository root (pyproject.toml not found)")


def get_app_version() -> str:
    """Get version from pyproject.toml or environment variable.

    Returns:
        str: Application version from environment variable, pyproject.toml, or default "0.0.0"
    """
    # First try to get from environment variable
    env_version = os.environ.get("APPLICATION_VERSION")
    if env_version:
        return env_version

    # Fall back to reading from pyproject.toml
    try:
        pyproject_path = os.path.join(REPO_ROOT, "pyproject.toml")
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data.get("project", {}).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


# Module-level constant for repository root
REPO_ROOT = get_repo_root()

service_name = os.environ.get("SERVICE_NAME", "ioc-cognition-fabric-node-svc")
