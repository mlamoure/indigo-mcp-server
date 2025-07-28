"""
Pytest configuration and fixtures for MCP server testing.
"""

import pytest
import tempfile
import os
import warnings
from typing import Generator

# Import tests package to set up path
import tests

# Validate required environment variables for testing
REQUIRED_ENV_VARS = [
    "OPENAI_API_KEY",
    "DB_FILE"
]

OPTIONAL_ENV_VARS = [
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY", 
    "LANGSMITH_PROJECT",
    "LARGE_MODEL",
    "SMALL_MODEL",
    "OPENAI_EMBEDDING_MODEL"
]

def validate_test_environment():
    """Validate that required environment variables are set for testing."""
    missing_vars = []
    for var in REQUIRED_ENV_VARS:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        warnings.warn(
            f"Missing required environment variables: {', '.join(missing_vars)}. "
            "Some tests may fail. Check your .env file.",
            UserWarning
        )
    
    # Special handling for DB_FILE - set a default temp path if not set
    if not os.environ.get("DB_FILE"):
        temp_db_default = "/tmp/test_vector_db"
        os.environ["DB_FILE"] = temp_db_default
        print(f"⚠ DB_FILE not set, using temporary default: {temp_db_default}")
    
    # Log available optional variables
    available_optional = [var for var in OPTIONAL_ENV_VARS if os.environ.get(var)]
    if available_optional:
        print(f"✓ Optional environment variables available: {', '.join(available_optional)}")

# Run validation when conftest is loaded
validate_test_environment()

from tests.mocks.mock_data_provider import MockDataProvider
from tests.mocks.mock_vector_store import MockVectorStore
from mcp_server.tools.search_entities import SearchEntitiesHandler, QueryParser, ResultFormatter
from mcp_server.common.vector_store.main import VectorStore


@pytest.fixture
def mock_data_provider() -> MockDataProvider:
    """Provide a mock data provider for testing."""
    return MockDataProvider()


@pytest.fixture
def mock_vector_store() -> MockVectorStore:
    """Provide a mock vector store for testing."""
    return MockVectorStore()


@pytest.fixture
def real_vector_store(temp_db_path) -> Generator[VectorStore, None, None]:
    """Provide a real vector store with temporary database for testing."""
    vector_store = VectorStore(db_path=temp_db_path)
    try:
        yield vector_store
    finally:
        # Cleanup
        try:
            vector_store.close()
        except Exception as e:
            print(f"Warning: Error closing vector store: {e}")


@pytest.fixture
def search_handler(mock_data_provider: MockDataProvider, real_vector_store: VectorStore) -> SearchEntitiesHandler:
    """Provide a search handler with real vector store and mock data provider."""
    return SearchEntitiesHandler(
        data_provider=mock_data_provider,
        vector_store=real_vector_store
    )


@pytest.fixture
def search_handler_with_mocks(mock_data_provider: MockDataProvider, mock_vector_store: MockVectorStore) -> SearchEntitiesHandler:
    """Provide a search handler with mock dependencies (for tests that need mocks)."""
    return SearchEntitiesHandler(
        data_provider=mock_data_provider,
        vector_store=mock_vector_store
    )


@pytest.fixture
def query_parser() -> QueryParser:
    """Provide a query parser for testing."""
    return QueryParser()


@pytest.fixture
def result_formatter() -> ResultFormatter:
    """Provide a result formatter for testing."""
    return ResultFormatter()


@pytest.fixture
def sample_search_results() -> dict:
    """Provide sample search results for testing."""
    return {
        "devices": [
            {
                "id": 1,
                "name": "Living Room Light",
                "type": "dimmer",
                "model": "Dimmer Switch",
                "address": "A1",
                "_similarity_score": 0.9
            },
            {
                "id": 2,
                "name": "Kitchen Light",
                "type": "switch",
                "model": "On/Off Switch",
                "address": "A2",
                "_similarity_score": 0.8
            }
        ],
        "variables": [
            {
                "id": 101,
                "name": "House Mode",
                "value": "Home",
                "folderId": 1,
                "_similarity_score": 0.7
            }
        ],
        "actions": []
    }


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Provide a temporary database path for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield os.path.join(temp_dir, "test_vector_db")


@pytest.fixture
def populated_mock_vector_store(mock_data_provider: MockDataProvider) -> MockVectorStore:
    """Provide a mock vector store populated with test data."""
    vector_store = MockVectorStore()
    
    # Populate with data from mock data provider
    vector_store.update_embeddings(
        devices=mock_data_provider.get_all_devices(),
        variables=mock_data_provider.get_all_variables(),
        actions=mock_data_provider.get_all_actions()
    )
    
    return vector_store


@pytest.fixture
def populated_real_vector_store(mock_data_provider: MockDataProvider, real_vector_store: VectorStore) -> VectorStore:
    """Provide a real vector store populated with test data."""
    # Populate with data from mock data provider
    real_vector_store.update_embeddings(
        devices=mock_data_provider.get_all_devices(),
        variables=mock_data_provider.get_all_variables(),
        actions=mock_data_provider.get_all_actions()
    )
    
    return real_vector_store