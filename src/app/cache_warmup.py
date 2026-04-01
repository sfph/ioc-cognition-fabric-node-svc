# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0

"""FAISS cache warmup - populate caches for all MAS from knowledge graph."""

import asyncio
import logging
from typing import Any, Callable, Dict, List

from caching.app.agent.caching_layer_manager import CachingLayerManager
from ingestion.app.agent.concept_vector_store import VectorStore
from knowledge_memory.server.database.graph_db.agensgraph.src.db import GraphDB
from knowledge_memory.server.schemas.knowledge_graph import Concept, EmbeddingConfig

from src.app.config.config import MGMT_URL
from src.app.utils.mgmt_plane_client import fetch_cfn_summary

logger = logging.getLogger(__name__)


async def query_all_concepts_for_mas(mas_id: str) -> List[Concept]:
    """
    Query ALL concepts from the knowledge graph for a given MAS.

    This directly queries the AgensGraph database to get all nodes (concepts)
    for a MAS graph, bypassing the query_knowledge_graph_async which requires
    specific concept IDs.

    Args:
        mas_id: Multi-Agentic System ID (used as graph name)

    Returns:
        List of Concept objects with embeddings

    Raises:
        Exception: If database query fails
    """

    def _sync_query():
        """Synchronous database query (run in thread pool)."""
        db = GraphDB()
        # Graph naming convention from adapter_graphdb_agensgraph.py:
        # mas_id with hyphens replaced by underscores, prefixed with "graph_"
        graph_name = f"graph_{mas_id.replace('-', '_')}"

        try:
            # Validate graph exists
            if not db.get_graph(graph_name):
                logger.warning(
                    f"Graph {graph_name} does not exist, MAS {mas_id} may not have data yet"
                )
                return []

            with db.engine.connect() as conn:
                # Set graph path
                conn.exec_driver_sql(f'SET graph_path = "{graph_name}"')

                # Query all vertices (nodes/concepts) in the graph
                # Cypher query to match all vertices and return their properties
                query = """
                MATCH (n)
                RETURN properties(n) as node_props
                """

                result = conn.exec_driver_sql(query)
                rows = result.fetchall()

                concepts = []
                for row in rows:
                    node_props = row[0] if row else {}

                    if not node_props or not isinstance(node_props, dict):
                        continue

                    # Parse embedding data
                    embeddings = None
                    if (
                        "embedding_vector" in node_props
                        and "embedding_model" in node_props
                    ):
                        embedding_vector = node_props.get("embedding_vector", [])
                        embedding_model = node_props.get("embedding_model", "")

                        # Handle JSON string parsing if needed
                        if isinstance(embedding_vector, str):
                            import json

                            try:
                                embedding_vector = json.loads(embedding_vector)
                            except (json.JSONDecodeError, ValueError):
                                pass

                        if embedding_vector:
                            embeddings = EmbeddingConfig(
                                data=embedding_vector, name=embedding_model
                            )

                    # Parse tags if present
                    tags = node_props.get("tags", [])
                    if isinstance(tags, str):
                        import json

                        try:
                            tags = json.loads(tags)
                        except (json.JSONDecodeError, ValueError):
                            tags = []

                    # Build Concept object
                    concept = Concept(
                        id=node_props.get("id", ""),
                        name=node_props.get("name", ""),
                        description=node_props.get("description"),
                        attributes={
                            k: v
                            for k, v in node_props.items()
                            if k
                            not in [
                                "id",
                                "name",
                                "description",
                                "embedding_vector",
                                "embedding_model",
                                "embeddings",
                                "tags",
                            ]
                        },
                        embeddings=embeddings,
                        tags=tags,
                    )
                    concepts.append(concept)

                logger.info(
                    f"Retrieved {len(concepts)} concepts from graph {graph_name}, "
                    f"{sum(1 for c in concepts if c.embeddings)} with embeddings"
                )
                return concepts

        except Exception as exc:
            logger.error(
                f"Failed to query graph {graph_name}: {type(exc).__name__}: {exc}",
                exc_info=True,
            )
            raise

    # Run synchronous database query in thread pool
    return await asyncio.to_thread(_sync_query)


def extract_mas_ids_from_summary(summary: Dict[str, Any]) -> List[str]:
    """
    Extract all MAS IDs from the CFN summary response.

    Args:
        summary: CFN summary response dict from management plane API

    Returns:
        List of MAS IDs
    """
    mas_ids = []
    workspace_to_masids = {}

    # Navigate: summary -> config -> workspaces -> multi_agentic_systems
    config = summary.get("config", {})
    for workspace in config.get("workspaces", []):
        for mas in workspace.get("multi_agentic_systems", []):
            mas_id = mas.get("id")
            if mas_id:
                mas_ids.append(mas_id)
        workspace_to_masids[workspace.get("id")] = mas_ids

    logger.debug(
        f"Workspace to MAS IDs: {workspace_to_masids}",
    )
    return mas_ids


def transform_concepts_to_vector_store_format(
    concepts: List[Concept],
) -> List[Dict[str, Any]]:
    """
    Transform Concept objects into format expected by ConceptVectorStore.

    Args:
        concepts: List of Concept objects from query_all_concepts_for_mas

    Returns:
        List of concept dicts with structure:
        {
            "id": str,
            "name": str,
            "description": str,
            "attributes": {
                "embedding": [[float...]]  # Note: double-nested list
            }
        }
    """
    concept_dicts = []

    for concept in concepts:
        concept_dict = {
            "id": concept.id,
            "name": concept.name,
            "description": concept.description or "",
            "attributes": concept.attributes or {},
        }

        # Extract embeddings if present
        # embeddings is an EmbeddingConfig object: {name: str, data: List[float]}
        if concept.embeddings and concept.embeddings.data:
            # Store in format expected by ConceptVectorStore: [[floats...]]
            concept_dict["attributes"]["embedding"] = [concept.embeddings.data]

        concept_dicts.append(concept_dict)

    return concept_dicts


async def populate_faiss_cache_for_mas(
    mas_id: str,
    cache_manager: CachingLayerManager,
    embed_fn: Callable,
) -> None:
    """
    Warm FAISS cache for a single MAS by loading all its concepts from knowledge graph.

    Queries the AgensGraph database directly to get ALL concepts for the MAS,
    then stores them in the FAISS cache for fast vector similarity search.

    Args:
        mas_id: Multi-Agentic System ID
        cache_manager: The global CachingLayerManager instance
        embed_fn: Embedding function for the cache layer
    """
    try:
        # Query ALL concepts from knowledge graph for this MAS
        concepts = await query_all_concepts_for_mas(mas_id)

        if not concepts:
            logger.warning(f"No concepts found for MAS {mas_id}, skipping cache warmup")
            return

        # Get or create cache layer for this MAS
        layer = cache_manager.get_cache(mas_id)
        if layer is None:
            logger.debug(f"Creating new FAISS cache layer for MAS {mas_id}")
            layer = cache_manager.create_cache(
                cache_id=mas_id,
                vector_dimension=384,  # bge-small-en-v1.5 dimension
                metric="l2",
                embed_fn=embed_fn,
            )
        else:
            logger.debug(f"Using existing cache layer for MAS {mas_id}")

        # Transform Concept objects to dict format for ConceptVectorStore
        concept_dicts = transform_concepts_to_vector_store_format(concepts)

        concepts_with_embeddings = sum(
            1 for c in concept_dicts if c.get("attributes", {}).get("embedding")
        )
        logger.debug(
            f"MAS {mas_id}: {concepts_with_embeddings}/{len(concept_dicts)} "
            f"concepts have embeddings"
        )

        # Store concepts in FAISS
        vector_store = VectorStore(cache_layer=layer)
        vector_store.store_concepts(concept_dicts)

        cache_stats = layer.describe()
        logger.info(
            f"Cache warmup completed for MAS {mas_id}: loaded {len(concept_dicts)} concepts, "
            f"FAISS index size={cache_stats['ntotal']}"
        )

    except Exception as exc:
        logger.error(
            f"Cache warmup failed for MAS {mas_id}: {type(exc).__name__}: {exc}",
            exc_info=True,
        )
        raise


def debug_cache_manager_state(
    cache_manager: CachingLayerManager,
    mas_ids: List[str],
) -> None:
    """
    Log detailed cache manager state for debugging purposes.

    Only logs if logger is set to DEBUG level or lower.

    Args:
        cache_manager: The CachingLayerManager instance to inspect
        mas_ids: List of MAS IDs to check
    """
    if not logger.isEnabledFor(logging.DEBUG):
        return

    logger.debug(f"Cache manager state: {len(mas_ids)} total MAS")
    for mas_id in mas_ids:
        layer = cache_manager.get_cache(mas_id)
        if layer:
            stats = layer.describe()
            logger.debug(
                f"MAS {mas_id}: FAISS index size={stats.get('ntotal', 0)}, "
                f"dimension={stats.get('d', 0)}"
            )
        else:
            logger.debug(f"MAS {mas_id}: No cache layer created")


async def warm_all_faiss_caches(
    cfn_id: str,
    cache_manager: CachingLayerManager,
    embed_fn: Callable,
) -> None:
    """
    Populate FAISS caches for all MAS in parallel.

    Fetches CFN summary from management plane API, extracts all MAS IDs,
    and warms the cache for each MAS by loading concepts from knowledge graph.

    Args:
        cfn_id: Cognition Fabric Node ID
        cache_manager: The global CachingLayerManager instance
        embed_fn: Embedding function for the cache layers
    """
    logger.info(f"Starting FAISS cache warmup for CFN {cfn_id}")

    # Fetch CFN summary from management plane
    try:
        summary = await fetch_cfn_summary(cfn_id)
        logger.debug("Fetched CFN summary from management plane")
    except Exception as exc:
        logger.error(f"Failed to fetch CFN summary: {exc}")
        raise

    # Extract all MAS IDs from summary
    mas_ids = extract_mas_ids_from_summary(summary)

    if not mas_ids:
        logger.warning("No MAS found in CFN configuration, skipping cache warmup")
        return

    logger.info(f"Found {len(mas_ids)} MAS to warm: {mas_ids}")

    # Populate all caches in parallel
    tasks = [
        populate_faiss_cache_for_mas(mas_id, cache_manager, embed_fn)
        for mas_id in mas_ids
    ]

    await asyncio.gather(*tasks, return_exceptions=True)

    # Debug: Log final cache manager state
    debug_cache_manager_state(cache_manager, mas_ids)
