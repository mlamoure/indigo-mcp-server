"""
Optimized IndigoQueryAgent package.

Provides intelligent home automation data retrieval with:
- High-performance caching with background refresh
- Semantic vector search via LanceDB integration  
- Device property compression for efficient data transfer
- Parallel API calls for reduced latency
"""

from .main import IndigoQueryAgent
from .cache_manager import IndigoItemsCache

__all__ = [
    "IndigoQueryAgent",
    "IndigoItemsCache",
]