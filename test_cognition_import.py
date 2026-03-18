"""
Test script to verify cognition-engine package imports
"""

def test_imports():
    """Test importing various modules from the cognition-engine package"""

    print("=" * 60)
    print("Testing cognition-engine package imports...")
    print("=" * 60)

    # Test 1: Knowledge Extraction imports
    print("\n1. Testing Knowledge Extraction imports:")
    try:
        from ingestion.app.agent.service import ConceptRelationshipExtractionService
        print("   ✓ ConceptRelationshipExtractionService imported")
    except ImportError as e:
        print(f"   ✗ ConceptRelationshipExtractionService: {e}")

    try:
        from ingestion.app.agent.concept_vector_store import ConceptVectorStore
        print("   ✓ ConceptVectorStore imported")
    except ImportError as e:
        print(f"   ✗ ConceptVectorStore: {e}")

    try:
        from ingestion.app.agent.processors import KnowledgeProcessor
        print("   ✓ KnowledgeProcessor imported")
    except ImportError as e:
        print(f"   ✗ KnowledgeProcessor: {e}")

    try:
        from ingestion.app.config.settings import Settings
        print("   ✓ Settings imported")
    except ImportError as e:
        print(f"   ✗ Settings: {e}")

    # Test 2: Evidence Gathering imports
    print("\n2. Testing Evidence Gathering imports:")
    try:
        from evidence.app.agent.evidence import process_evidence
        print("   ✓ process_evidence imported")
    except ImportError as e:
        print(f"   ✗ process_evidence: {e}")

    try:
        from evidence.app.api.schemas import ReasonerCognitionRequest, Header, ReasonerPayload
        print("   ✓ ReasonerCognitionRequest, Header, ReasonerPayload imported")
    except ImportError as e:
        print(f"   ✗ ReasonerCognitionRequest, Header, ReasonerPayload: {e}")

    try:
        from evidence.app.data.mock_repo import MockDataRepository
        print("   ✓ MockDataRepository imported")
    except ImportError as e:
        print(f"   ✗ MockDataRepository: {e}")

    # Test 3: Caching Layer imports
    print("\n3. Testing Caching Layer imports:")
    try:
        from caching.app.agent.caching_layer import CachingLayer
        print("   ✓ CachingLayer imported")
    except ImportError as e:
        print(f"   ✗ CachingLayer: {e}")

    try:
        from caching.app.models.cache_models import ConceptData
        print("   ✓ ConceptData imported")
    except ImportError as e:
        print(f"   ✗ ConceptData: {e}")

    # Test 4: Gateway/Registration imports
    print("\n4. Testing Gateway/Registration imports:")
    try:
        from gateway import register_both_engines
        print("   ✓ register_both_engines imported")
    except ImportError as e:
        print(f"   ✗ register_both_engines: {e}")

    try:
        from gateway import register_knowledge_management_engine, register_semantic_negotiation_engine
        print("   ✓ register_knowledge_management_engine, register_semantic_negotiation_engine imported")
    except ImportError as e:
        print(f"   ✗ register_knowledge_management_engine, register_semantic_negotiation_engine: {e}")

    # Test 5: Embedding Manager
    print("\n5. Testing Embedding Manager imports:")
    try:
        from evidence.app.agent.embeddings import EmbeddingManager
        print("   ✓ EmbeddingManager imported")
    except ImportError as e:
        print(f"   ✗ EmbeddingManager: {e}")

    print("\n" + "=" * 60)
    print("Import test complete!")
    print("=" * 60)

if __name__ == "__main__":
    test_imports()
