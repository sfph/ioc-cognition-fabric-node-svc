# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

import asyncio
import os
from contextlib import asynccontextmanager
import uvicorn
import logging

from caching.app.agent import CachingLayer
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from gateway import register_both_engines
from ingestion.app.agent.knowledge_processor import EmbeddingManager
from ingestion.app.config.settings import Settings

from src.app.api.router import router as api_router
from src.app.registration import register_on_startup, get_outbound_ip
from src.app.utils.utils import REPO_ROOT, service_name, get_app_version
from src.logger.logger import setup_logging

from knowledge_memory.bootstrap.database import DatabaseManager
from knowledge_memory.bootstrap.provider import register_provider

stop_event = asyncio.Event()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def km_lifespan(
    app: FastAPI,
    *,
    db_name: str | None = None,
    user: str | None = None,
    password: str | None = None,
    host: str | None = None,
    port: int | None = None,
    register_provider_enabled: bool = True,
    provider_config: dict | None = None,
):
    db_manager = DatabaseManager(
        db_name=db_name,
        user=user,
        password=password,
        host=host,
        port=port,
    )

    if register_provider_enabled and provider_config:
        try:
            register_provider(**provider_config)
        except Exception as exc:
            logger.warning(
                "Memory provider registration failed, continuing startup: %s",
                exc,
            )

    db_manager.start()
    app.state.db_manager = db_manager

    try:
        yield
    finally:
        logger.info("Shutting down database connections")
        db_manager.stop()


@asynccontextmanager
async def cognition_engine_lifespan(app: FastAPI):
    await register_both_engines(
        mgmt_plane_url=os.environ.get("MGMT_URL", "http://localhost:9000"),
        engine_host=get_outbound_ip(),
        engine_port=int(os.environ.get("PORT", 9002))
    )

    embedding_manager = EmbeddingManager()

    def embed_fn(text: str):
        out = embedding_manager.generate_embedding(text)
        if out is None:
            raise ValueError("Embedding returned None")
        return out

    cache_layer = CachingLayer(
        vector_dimension=384,  # bge-small-en-v1.5 dimension
        metric="l2",
        embed_fn=embed_fn,
    )

    app.state.embedding_manager = embedding_manager
    app.state.cache_layer = cache_layer
    app.state.settings = Settings()

    try:
        yield
    finally:
        logger.info("Cognition engine shutdown complete")


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    await register_on_startup(
        app_port=int(os.environ.get("PORT", 9002)),
        stop_event=stop_event,
    )

    provider_config = {
        "provider_name": "ioc-memory-provider",
        "description": "Memory provider with graph + vector support",
        "service_host": get_outbound_ip(),
        "service_port": os.environ.get("PORT", "9002"),
        "registration_url": os.environ.get("MGMT_URL", "localhost:9002"),
    }

    async with km_lifespan(
        app,
        db_name=os.environ.get("DB_NAME"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        host=os.environ.get("DB_HOST"),
        port=int(os.environ.get("DB_PORT", 5432)),
        register_provider_enabled=True,
        provider_config=provider_config,
    ):
        async with cognition_engine_lifespan(app):
            yield

    stop_event.set()


def create_app(*, lifespan=None) -> FastAPI:
    # Load env first
    if os.environ.get("ENV", "").lower() != "prod":
        load_dotenv(dotenv_path=f"{REPO_ROOT}/env.conf", override=False)

    # Configure logging once
    setup_logging(service_name)
    logger = logging.getLogger(__name__)
    logger.info("Environment variables loaded")

    app = FastAPI(
        title=f"{service_name} API",
        version=get_app_version(),
        description="IoC Cognition Fabrics Node Service API",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan or app_lifespan,
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

    version = get_app_version()

    port = int(os.environ.get("PORT", 9002))
    uvicorn.run(app, host="0.0.0.0", port=port, log_config=None)
