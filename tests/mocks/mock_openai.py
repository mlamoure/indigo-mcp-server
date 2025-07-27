"""
Mock OpenAI client for testing.
"""

import json
import hashlib
from typing import List, Dict, Any


class MockEmbeddingResponse:
    """Mock embedding response object."""
    
    def __init__(self, embeddings: List[List[float]]):
        self.data = [MockEmbedding(embedding) for embedding in embeddings]


class MockEmbedding:
    """Mock embedding object."""
    
    def __init__(self, embedding: List[float]):
        self.embedding = embedding


class MockOpenAIClient:
    """Mock OpenAI client for testing."""
    
    def __init__(self, dimension: int = 1536):
        """Initialize mock client."""
        self.dimension = dimension
        self.embeddings = MockEmbeddings()
    
    def create_deterministic_embedding(self, text: str) -> List[float]:
        """Create a deterministic embedding based on text hash."""
        # Create a hash of the text
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        # Convert hash to numbers and normalize to create embedding
        embedding = []
        for i in range(0, len(text_hash), 2):
            # Take pairs of hex characters and convert to float
            hex_pair = text_hash[i:i+2]
            value = int(hex_pair, 16) / 255.0  # Normalize to 0-1
            embedding.append(value - 0.5)  # Center around 0
        
        # Pad or truncate to desired dimension
        while len(embedding) < self.dimension:
            embedding.extend(embedding[:min(len(embedding), self.dimension - len(embedding))])
        
        return embedding[:self.dimension]


class MockEmbeddings:
    """Mock embeddings API."""
    
    def __init__(self):
        self.client = None
    
    def create(self, input: List[str], model: str = "text-embedding-3-small") -> MockEmbeddingResponse:
        """Create mock embeddings for input texts."""
        mock_client = MockOpenAIClient()
        embeddings = [mock_client.create_deterministic_embedding(text) for text in input]
        return MockEmbeddingResponse(embeddings)