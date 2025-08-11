"""
Test fixtures using real Indigo data (or realistic sample data).
"""

import json
import os
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

from ..utils.indigo_data_fetcher import create_indigo_fetcher_from_env

logger = logging.getLogger(__name__)

# Path to the fixtures directory
FIXTURES_DIR = Path(__file__).parent
SAMPLE_DATA_FILE = FIXTURES_DIR / "real_indigo_sample_data.json"


class IndigoDataFixtures:
    """Provides real or sample Indigo data for testing."""
    
    def __init__(self):
        """Initialize with either real data fetcher or sample data."""
        self._real_data_cache = None
        self._sample_data_cache = None
        
        # Try to create real data fetcher
        self._fetcher = create_indigo_fetcher_from_env()
        if self._fetcher:
            logger.info("✅ Real Indigo API connection available for testing")
        else:
            logger.info("📝 Using sample data for testing (no Indigo API connection)")
    
    def get_sample_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get sample data from JSON file."""
        if self._sample_data_cache is None:
            try:
                with open(SAMPLE_DATA_FILE, 'r') as f:
                    self._sample_data_cache = json.load(f)
                logger.debug(f"Loaded sample data from {SAMPLE_DATA_FILE}")
            except Exception as e:
                logger.error(f"Failed to load sample data: {e}")
                # Fallback to minimal data
                self._sample_data_cache = {
                    "devices": [],
                    "variables": [],
                    "actions": []
                }
        
        return self._sample_data_cache
    
    def get_real_data(self, device_limit: int = 10, variable_limit: int = 5, 
                     action_limit: int = 5) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """
        Get real data from Indigo API.
        
        Returns None if API is not available.
        """
        if not self._fetcher:
            return None
        
        if self._real_data_cache is None:
            try:
                self._real_data_cache = self._fetcher.fetch_sample_data(
                    device_limit, variable_limit, action_limit
                )
                logger.info(f"Fetched real data: {len(self._real_data_cache['devices'])} devices, "
                          f"{len(self._real_data_cache['variables'])} variables, "
                          f"{len(self._real_data_cache['actions'])} actions")
            except Exception as e:
                logger.error(f"Failed to fetch real data: {e}")
                self._real_data_cache = None
        
        return self._real_data_cache
    
    def get_test_data(self, prefer_real: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get test data, preferring real data if available and requested.
        
        Args:
            prefer_real: If True, try to get real data first
            
        Returns:
            Dictionary with devices, variables, actions lists
        """
        if prefer_real:
            real_data = self.get_real_data()
            if real_data:
                return real_data
        
        return self.get_sample_data()
    
    def get_devices(self, prefer_real: bool = False) -> List[Dict[str, Any]]:
        """Get device data for testing."""
        return self.get_test_data(prefer_real)["devices"]
    
    def get_variables(self, prefer_real: bool = False) -> List[Dict[str, Any]]:
        """Get variable data for testing.""" 
        return self.get_test_data(prefer_real)["variables"]
    
    def get_actions(self, prefer_real: bool = False) -> List[Dict[str, Any]]:
        """Get action data for testing."""
        return self.get_test_data(prefer_real)["actions"]
    
    def create_real_vector_store_with_data(self, vector_store, prefer_real: bool = True) -> bool:
        """
        Populate a vector store with real test data and embeddings.
        
        Args:
            vector_store: VectorStore instance to populate
            prefer_real: Whether to prefer real data over sample data
            
        Returns:
            True if successful, False otherwise
        """
        try:
            data = self.get_test_data(prefer_real)
            
            # Only populate if we have data
            if not any(data.values()):
                logger.warning("No test data available to populate vector store")
                return False
            
            # Update embeddings with real data - this will create actual embeddings using OpenAI
            logger.info("🔄 Creating embeddings for test data (this may take a moment)...")
            vector_store.update_embeddings(
                devices=data["devices"],
                variables=data["variables"], 
                actions=data["actions"]
            )
            
            logger.info("✅ Vector store populated with real test data and embeddings")
            return True
            
        except Exception as e:
            logger.error(f"Failed to populate vector store: {e}")
            return False


# Global instance for easy access
indigo_fixtures = IndigoDataFixtures()


def get_real_indigo_devices() -> List[Dict[str, Any]]:
    """Get real or sample Indigo devices."""
    return indigo_fixtures.get_devices(prefer_real=True)


def get_real_indigo_variables() -> List[Dict[str, Any]]:
    """Get real or sample Indigo variables."""
    return indigo_fixtures.get_variables(prefer_real=True)


def get_real_indigo_actions() -> List[Dict[str, Any]]:
    """Get real or sample Indigo actions."""
    return indigo_fixtures.get_actions(prefer_real=True)


def get_sample_indigo_data() -> Dict[str, List[Dict[str, Any]]]:
    """Get sample Indigo data (always uses sample, not real API)."""
    return indigo_fixtures.get_sample_data()