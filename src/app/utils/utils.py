# Copyright 2026 Cisco Systems, Inc. and its affiliates
#
# SPDX-License-Identifier: Apache-2.0
import json
import logging
import os
import tomllib
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from fastapi import HTTPException
from ingestion.app.agent.concept_vector_store import VectorStore
from knowledge_memory import upsert_knowledge_graph_async
from starlette import status

logger = logging.getLogger(__name__)


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
        pyproject_path = os.path.join(get_repo_root(), "pyproject.toml")
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data.get("project", {}).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def bootstrap_env() -> None:
    if os.environ.get("ENV", "").lower() != "prod":
        load_dotenv(dotenv_path=f"{get_repo_root()}/env.conf", override=False)


def json_escape_string(value: str) -> str:
    return json.dumps(value)[1:-1]


def transform_concept_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    # Required / known field
    out["concept_type"] = attrs.get("conceptType")

    # Extra attributes
    for k, v in attrs.get("extra", {}).items():
        out[k] = v

    return out


def transform_concept_embedding(attrs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    embedding = attrs.get("embedding")

    if not embedding or not embedding[0]:
        return None

    return {
        "name": "ibm-granite/granite-embedding-30m-english",  # TODO: make dynamic
        "data": embedding[0],
    }


def transform_extraction_concepts(
    src: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    if not src:
        return None

    out: List[Dict[str, Any]] = []

    for c in src:
        description = c.get("description", "")
        desc_value = None

        # Preserve empty string vs nil semantics
        if description:
            desc_value = json_escape_string(description)

        out.append(
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "description": desc_value,
                "attributes": transform_concept_attributes(c.get("attributes", {})),
                "embeddings": transform_concept_embedding(c.get("attributes", {})),
            }
        )

    return out


def transform_extraction_relations(
    src: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    if not src:
        return None

    out: List[Dict[str, Any]] = []

    for r in src:
        out.append(
            {
                "id": r.get("id"),
                "relation": r.get("relationship"),
                "node_ids": r.get("node_ids"),
                "attributes": r.get("attributes"),
            }
        )

    return out


async def upsert_shared_memories_to_db_and_cache(
    mas_id: str,
    workspace_id: str,
    request_id: str,
    result: Dict[str, Any],
    vector_store: VectorStore,
    force_replace: bool = True,
):
    try:
        concepts = transform_extraction_concepts(result.get("concepts", []))
        relations = transform_extraction_relations(result.get("relations", []))
        rag_chunks = transform_extraction_relations(result.get("rag_chunks", []))

        logger.debug("Concepts from extraction: %s", concepts)
        logger.debug("Relations from extraction: %s", relations)
        logger.debug("RAG chunks from extraction: %s", rag_chunks)

        kg_resp = await upsert_knowledge_graph_async(
            mas_id=mas_id,
            wksp_id=workspace_id,
            request_id=request_id,
            concepts=concepts,
            relations=relations,
            force_replace=force_replace,
        )

        logger.info(f"create or update shared memories to DB succeeded: {kg_resp}")

        # only write to cache to ensure data consistency between DB and cache
        vector_store.store_concepts(result.get("concepts", []))
        vector_store.store_rag_chunks(result.get("rag_chunks", []))

        logger.info("create or update shared memories to cache succeeded")

        return kg_resp

    except Exception as exc:
        logger.exception(
            "Failed to create or update data to knowledge graph DB or cache | workspace=%s mas=%s",
            workspace_id,
            mas_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"failed to create or update shared memories, error: {exc}",
        )
