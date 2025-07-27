"""
Pytest configuration and fixtures for MCP server testing.
"""

import pytest
import tempfile
import os
from typing import Generator

from tests.mocks.mock_data_provider import MockDataProvider
from tests.mocks.mock_vector_store import MockVectorStore
from mcp_server.tools.search_entities import SearchEntitiesHandler
from mcp_server.tools.query_parser import QueryParser
from mcp_server.tools.result_formatter import ResultFormatter


@pytest.fixture
def mock_data_provider() -> MockDataProvider:
    """Provide a mock data provider for testing."""
    return MockDataProvider()


@pytest.fixture
def mock_vector_store() -> MockVectorStore:
    """Provide a mock vector store for testing."""
    return MockVectorStore()


@pytest.fixture
def search_handler(mock_data_provider: MockDataProvider, mock_vector_store: MockVectorStore) -> SearchEntitiesHandler:
    """Provide a search handler with mock dependencies."""
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