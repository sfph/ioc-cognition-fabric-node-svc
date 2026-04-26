# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

from src.app.utils.utils import bootstrap_env

bootstrap_env()

import asyncio
import os
from contextlib import asynccontextmanager
import uvicorn
import logging

from caching.app.agent.caching_layer_manager import CachingLayerManager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from gateway import register_both_engines
from ingestion.app.agent.knowledge_processor import EmbeddingManager
from ingestion.app.config.settings import Settings

from src.app.api.router import router as api_router
from src.app.registration import register_on_startup, get_outbound_ip
from src.app.cache_warmup import warm_all_faiss_caches
from src.app.utils.mgmt_plane_client import fetch_all_cfn_nodes
from src.app.utils.utils import get_app_version
from src.logger.logger import setup_logging

from src.app.config.config import (
    MGMT_URL,
    APP_PORT,
    WARMUP_TIMEOUT_SECONDS,
    CFN_NAME,
    DB_NAME,
    DB_USER,
    DB_HOST,
    DB_PASSWORD,
    DB_PORT,
    LOG_LEVEL,
    SERVICE_NAME,
    validate_db_config,
)

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
        mgmt_plane_url=MGMT_URL,
        engine_host=get_outbound_ip(),
        engine_port=int(APP_PORT),
    )

    embedding_manager = EmbeddingManager()

    def embed_fn(text: str):
        out = embedding_manager.generate_embedding(text)
        if out is None:
            raise ValueError("Embedding returned None")
        return out

    # Create manager instead of single layer for mas_id-based isolation
    vector_cache_manager = CachingLayerManager()

    # Cache Manager for Graph
    app.state.embedding_manager = embedding_manager
    app.state.vector_cache_manager = vector_cache_manager

    # Cache Manager for RAG
    rag_cache_manager = CachingLayerManager()
    app.state.rag_cache_manager = rag_cache_manager

    app.state.embed_fn = embed_fn
    app.state.settings = Settings()

    # Warm FAISS caches for all MAS (blocking to ensure cache is ready)
    warmup_timeout = int(WARMUP_TIMEOUT_SECONDS)

    async def warmup_task():
        logger.info(
            f"FAISS cache warmup: Looking up CFN by name '{CFN_NAME}' from {MGMT_URL}"
        )

        # Fetch all CFN nodes and find ours by name
        cfn_list = await fetch_all_cfn_nodes()
        matching_cfn = None

        for node in cfn_list.get("nodes", []):
            if node.get("cfn_name") == CFN_NAME:
                matching_cfn = node
                break

        if not matching_cfn:
            logger.warning(
                f"FAISS cache warmup: Skipped - No CFN found with name '{CFN_NAME}'. "
                f"Found {len(cfn_list.get('nodes', []))} CFN(s) but none matched."
            )
            return

        cfn_id = matching_cfn.get("cfn_id")
        logger.debug(f"FAISS cache warmup: Found CFN '{CFN_NAME}' (id={cfn_id})")
        await warm_all_faiss_caches(cfn_id, vector_cache_manager, embed_fn)

    try:
        logger.info(f"Starting cache warmup with {warmup_timeout}s timeout")
        await asyncio.wait_for(warmup_task(), timeout=warmup_timeout)
    except asyncio.TimeoutError:
        logger.warning(
            f"Cache warmup timed out after {warmup_timeout}s. "
            f"Service will start with empty cache. Set WARMUP_TIMEOUT_SECONDS to increase."
        )
    except Exception as exc:
        logger.error(
            f"FAISS cache warmup: Failed to initialize - {type(exc).__name__}: {exc}",
            exc_info=True,
        )

    try:
        yield
    finally:
        logger.info("Cognition engine shutdown complete")


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    validate_db_config()

    await register_on_startup(stop_event=stop_event)

    provider_config = {
        "provider_name": "ioc-memory-provider",
        "description": "Memory provider with graph + vector support",
        "service_host": get_outbound_ip(),
        "service_port": APP_PORT,
        "registration_url": MGMT_URL,
    }

    async with km_lifespan(
        app,
        db_name=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=int(DB_PORT),
        register_provider_enabled=True,
        provider_config=provider_config,
    ):
        async with cognition_engine_lifespan(app):
            # Continuous loop-lag sampler with stack snapshots on wedge.
            from src.app.api._loop_lag import start_sampler, stop_sampler
            start_sampler()
            try:
                yield
            finally:
                await stop_sampler()

    stop_event.set()


def create_app(*, lifespan=None) -> FastAPI:
    # Configure logging once
    setup_logging(SERVICE_NAME)
    logger = logging.getLogger(__name__)
    logger.info("Environment variables loaded")

    app = FastAPI(
        title=f"{SERVICE_NAME} API",
        version=get_app_version(),
        description="IoC Cognition Fabrics Node Service API",
        docs_url="/api/docs",  # align API docs path with mgmt-plane-service
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

    # Per-request timing middleware.
    # Installs a fresh per-request timing dict that the dep factories and
    # the /decide route handler cooperate on.  Middleware-level so it
    # captures FastAPI ``Depends`` resolution time (which happens before
    # the route body runs and was previously invisible to handler-local
    # timing).
    import time as _time
    from src.app.api._request_timing import timing_reset, timing_stamp
    from src.app.api._loop_lag import loop_lag_window_start, loop_lag_window_stop

    @app.middleware("http")
    async def _stamp_request_start(request, call_next):
        bucket = timing_reset()
        timing_stamp("request_started_perf", _time.perf_counter())
        # Open per-request lag-sampling window.  The continuous background
        # sampler is always running; this just marks "what slice of its
        # samples belong to this request" so we can stamp summary stats
        # into the _timing envelope.
        loop_lag_window_start()
        # Compute wire-to-middleware delta from a client-supplied wall-clock
        # send time. If the gap between the client's POST and our middleware
        # firing is large, the request was either sitting on the wire or —
        # more likely — in uvicorn's accept queue waiting for the event
        # loop to free up.
        sent_ns_hdr = request.headers.get("x-client-sent-wall-ns")
        if sent_ns_hdr:
            try:
                sent_ns = int(sent_ns_hdr)
                wire_ms = (_time.time_ns() - sent_ns) / 1_000_000.0
                # Negative deltas from clock skew → clamp at 0 to avoid noise.
                timing_stamp("wire_to_middleware_ms", round(max(0.0, wire_ms), 2))
            except (ValueError, TypeError):
                pass  # never let a bad header break the request
        response = await call_next(request)
        # We can't mutate a streaming response body here; the handler
        # itself merges the bucket into ``_timing`` before returning.
        # Stamp the end so debug logs / future middleware can read it.
        bucket["request_finished_perf"] = _time.perf_counter()
        # Close the per-request lag window and emit summary stats via
        # response headers so the client can capture them alongside
        # ``cfn_call_timing``.  We don't try to mutate the response body
        # because the handler has already built and serialised it; headers
        # are still under our control here.
        lag_summary = loop_lag_window_stop()
        if lag_summary:
            for k, v in lag_summary.items():
                # Header values must be strings; client side casts back.
                response.headers[f"x-{k.replace('_', '-')}"] = str(v)
        return response

    app.include_router(api_router, prefix="/api")

    return app


app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=getattr(logging, LOG_LEVEL))

    version = get_app_version()

    uvicorn.run(app, host="0.0.0.0", port=int(APP_PORT), log_config=None)
