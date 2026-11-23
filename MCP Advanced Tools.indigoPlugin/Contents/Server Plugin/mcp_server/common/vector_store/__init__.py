"""
Vector store package for semantic search of Indigo entities.

Importing this package (or availability / vector_store_manager) does not
import lancedb: it is optional (Apple Silicon only, see availability.py), so
VectorStore and VectorStoreManager load on first attribute access.
"""

from .availability import SemanticSearchStatus, semantic_search_status

__all__ = ["SemanticSearchStatus", "VectorStore", "VectorStoreManager", "semantic_search_status"]


def __getattr__(name):
    if name == "VectorStore":
        from .main import VectorStore
        return VectorStore
    if name == "VectorStoreManager":
        from .vector_store_manager import VectorStoreManager
        return VectorStoreManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
