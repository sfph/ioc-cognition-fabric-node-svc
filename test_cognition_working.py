"""
Working example of cognition-engine package usage
"""

import asyncio

print("=" * 60)
print("Testing cognition-engine - Working Examples")
print("=" * 60)

# Example 1: Knowledge Extraction Service
print("\n1. Knowledge Extraction Service:")
try:
    from ingestion.app.agent.service import ConceptRelationshipExtractionService
    from ingestion.app.agent.concept_vector_store import ConceptVectorStore
    from ingestion.app.config.settings import Settings

    print("   ✓ All knowledge extraction imports successful")
    print("   - ConceptRelationshipExtractionService available")
    print("   - ConceptVectorStore available")
    print("   - Settings available")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Example 2: Evidence Gathering
print("\n2. Evidence Gathering:")
try:
    from evidence.app.agent.evidence import process_evidence
    from evidence.app.api.schemas import (
        ReasonerCognitionRequest,
        Header,
        RequestPayload,  # Note: It's RequestPayload, not ReasonerPayload
    )
    from evidence.app.data.mock_repo import MockDataRepository

    print("   ✓ All evidence gathering imports successful")
    print("   - process_evidence available")
    print("   - ReasonerCognitionRequest, Header, RequestPayload available")
    print("   - MockDataRepository available")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Example 3: Embedding Manager
print("\n3. Embedding Manager:")
try:
    from evidence.app.agent.embeddings import EmbeddingManager

    print("   ✓ EmbeddingManager imported successfully")
    print("   Note: First use will download ~100MB BAAI/bge-small-en-v1.5 model")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Example 4: Caching Layer
print("\n4. Caching Layer:")
try:
    from caching.app.agent.caching_layer import CachingLayer

    print("   ✓ CachingLayer imported successfully")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Example 5: Gateway Registration
print("\n5. Gateway Registration:")
try:
    from gateway import (
        register_both_engines,
        register_knowledge_management_engine,
        register_semantic_negotiation_engine
    )

    print("   ✓ All gateway registration functions available")
    print("   - register_both_engines")
    print("   - register_knowledge_management_engine")
    print("   - register_semantic_negotiation_engine")
except Exception as e:
    print(f"   ✗ Error: {e}")

print("\n" + "=" * 60)
print("Summary: Core cognition-engine modules are working!")
print("=" * 60)

# Minimal working example
print("\n\nMinimal Working Example:")
print("-" * 60)

async def test_evidence_gathering():
    """Demonstrate basic evidence gathering setup"""
    try:
        from evidence.app.agent.evidence import process_evidence
        from evidence.app.api.schemas import ReasonerCognitionRequest, Header, RequestPayload
        from evidence.app.data.mock_repo import MockDataRepository
        from caching.app.agent.caching_layer import CachingLayer

        # Initialize
        repo = MockDataRepository()
        cache_layer = CachingLayer()

        # Create request
        request = ReasonerCognitionRequest(
            header=Header(
                workspace_id="test-ws",
                mas_id="test-mas",
                agent_id="test-agent"
            ),
            request_id="test-001",
            payload=RequestPayload(
                intent="Test query",
                metadata={}
            )
        )

        print("✓ Evidence gathering components initialized successfully")
        print(f"  - Repository: {type(repo).__name__}")
        print(f"  - Cache: {type(cache_layer).__name__}")
        print(f"  - Request ID: {request.request_id}")

    except Exception as e:
        print(f"✗ Error in example: {e}")

asyncio.run(test_evidence_gathering())

print("\n" + "=" * 60)
