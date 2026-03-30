import os


def get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def validate_db_config() -> None:
    get_required_env("DB_NAME")
    get_required_env("DB_USER")
    get_required_env("DB_PASSWORD")
    get_required_env("DB_HOST")
    get_required_env("DB_PORT")


# General configurations
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()
DISABLE_REGISTRATION = os.getenv("DISABLE_REGISTRATION", "").lower() == "true"
DISABLE_VALIDATION = os.getenv("DISABLE_VALIDATION", "true").lower() == "true"

APP_PORT = os.environ.get("PORT", "9002")
CFN_NAME = os.environ.get("CFN_NAME", "cfn-local")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "ioc-cfn-svc")

WARMUP_TIMEOUT_SECONDS = os.environ.get("WARMUP_TIMEOUT_SECONDS", "300")
HEARTBEAT_INTERVAL_SECONDS = os.environ.get("HEARTBEAT_INTERVAL_SECONDS", "29")
MGMT_URL = os.environ.get("MGMT_URL", "http://localhost:9000")


# DB configurations
DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT")

# LLM credentials
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT")

# Other configurations
GIT_COMMIT_TIME = os.environ.get("GIT_COMMIT_TIME", "unknown")
GIT_COMMIT_SHA = os.environ.get("GIT_COMMIT_SHA", "unknown")
GIT_BRANCH = os.environ.get("GIT_BRANCH", "unknown")
