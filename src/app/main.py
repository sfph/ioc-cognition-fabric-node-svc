import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.app.api.router import router as api_router

from dotenv import load_dotenv

from src.app.registration import register_on_startup
from src.app.utils.utils import REPO_ROOT, service_name, get_app_version
from src.logger.logger import setup_logging

stop_event = asyncio.Event()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger(__name__)

    # ---- Startup logic ----
    logger.info("Starting up '%s'",service_name)

    await register_on_startup(
        app_port=int(os.environ.get("PORT", 9002)),
        stop_event=stop_event,
    )

    yield

    # ---- Shutdown logic ----
    logger.info("Shutting down the '%s' service", service_name)
    stop_event.set()


def create_app() -> FastAPI:
    # Load env first
    load_dotenv(dotenv_path=f"{REPO_ROOT}/env.conf", override=True)

    # Configure logging once
    setup_logging(service_name)
    logger = logging.getLogger(__name__)
    logger.info("Environment variables loaded")

    app = FastAPI(
        title=f"{service_name} API",
        version=get_app_version(),
        description="IoC CFN Management Backend Service API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    allowed_origins = os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    return app

app = create_app()

if __name__ == "__main__":
    log_level = os.environ.get("LOG_LEVEL", "DEBUG").upper()
    logging.basicConfig(level=getattr(logging, log_level))

    logger = logging.getLogger(__name__)

    version = get_app_version()

    port = int(os.environ.get("PORT", 9002))
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=None)
