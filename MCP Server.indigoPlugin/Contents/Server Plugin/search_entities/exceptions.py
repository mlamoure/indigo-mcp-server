"""
Custom exceptions for IndigoQueryAgent operations.

NOTE: Only exceptions actually used in the codebase are defined here.
Removed unused exceptions to reduce code clutter.
"""


class IndigoQueryAgentError(Exception):
    """Base exception for IndigoQueryAgent-related errors."""
    pass


class CacheError(IndigoQueryAgentError):
    """Base exception for cache-related errors."""
    pass


class CacheInitializationError(CacheError):
    """Raised when cache initialization fails.
    
    Used in main.py when the IndigoItemsCache cannot be created.
    """
    pass


class CacheRefreshError(CacheError):
    """Raised when cache refresh operations fail.
    
    Used in cache_manager.py when API calls or data processing fails.
    """
    pass


class ItemDetailsFetchError(IndigoQueryAgentError):
    """Raised when fetching item details fails.
    
    Used in main.py for manual cache refresh failures.
    """
    pass


class VectorSearchError(IndigoQueryAgentError):
    """Raised when vector search operations fail.
    
    Used in main.py when LanceDB search encounters errors.
    """
    pass


class DatabaseError(IndigoQueryAgentError):
    """Raised when database operations fail.
    
    Used for LanceDB initialization or connection errors.
    """
    pass