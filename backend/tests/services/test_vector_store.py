"""
Tests for the Vector Store component
"""
import pytest
import numpy as np
from unittest.mock import Mock, patch
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.vector_store import VectorStore
from app.core.config import settings

@pytest.fixture
def mock_db():
    """Mock SQLAlchemy session"""
    mock = Mock(spec=Session)
    mock.execute.return_value = Mock()
    mock.commit.return_value = None
    return mock

@pytest.fixture
def mock_embeddings():
    """Mock embeddings model"""
    mock = Mock()
    mock.embed_query.return_value = np.random.rand(384)  # Default dimension
    return mock

@pytest.fixture
def vector_store(mock_db, mock_embeddings):
    """Create VectorStore with mocked dependencies"""
    store = VectorStore(db=mock_db)
    store.embeddings = mock_embeddings
    return store

@pytest.mark.asyncio
async def test_add_document(vector_store, mock_db):
    """Test adding document to vector store"""
    content = "Test document content"
    metadata = {
        "document_id": 1,
        "fund_id": 1,
        "source": "test"
    }
    
    await vector_store.add_document(content, metadata)
    
    # Verify database calls
    assert mock_db.execute.called
    assert mock_db.commit.called
    
    # Check SQL query
    call_args = mock_db.execute.call_args
    sql = call_args[0][0]
    assert "INSERT INTO document_embeddings" in str(sql)
    
    # Check parameters
    params = call_args[1]
    assert params["document_id"] == 1
    assert params["fund_id"] == 1
    assert params["content"] == content

@pytest.mark.asyncio
async def test_similarity_search(vector_store, mock_db):
    """Test similarity search functionality"""
    query = "test query"
    k = 5
    filter_metadata = {"fund_id": 1}
    
    # Mock search results
    mock_result = Mock()
    mock_result.__iter__.return_value = [
        (1, 1, 1, "content 1", {"source": "doc1"}, 0.9),
        (2, 1, 1, "content 2", {"source": "doc2"}, 0.8)
    ]
    mock_db.execute.return_value = mock_result
    
    results = await vector_store.similarity_search(
        query=query,
        k=k,
        filter_metadata=filter_metadata
    )
    
    # Verify results
    assert len(results) == 2
    assert all(r["score"] > 0 for r in results)
    assert all("content" in r for r in results)
    assert all("metadata" in r for r in results)
    
    # Check SQL query
    call_args = mock_db.execute.call_args
    sql = str(call_args[0][0])
    assert "SELECT" in sql
    assert "ORDER BY embedding <=> :query_embedding::vector" in sql
    assert "LIMIT :k" in sql

@pytest.mark.asyncio
async def test_similarity_search_with_threshold(vector_store, mock_db):
    """Test similarity search with score threshold"""
    query = "test query"
    min_score = 0.5
    
    # Mock search results with varying scores
    mock_result = Mock()
    mock_result.__iter__.return_value = [
        (1, 1, 1, "content 1", {"source": "doc1"}, 0.9),
        (2, 1, 1, "content 2", {"source": "doc2"}, 0.4)  # Below threshold
    ]
    mock_db.execute.return_value = mock_result
    
    results = await vector_store.similarity_search(
        query=query,
        min_score=min_score
    )
    
    # Should only return results above threshold
    assert len(results) == 1
    assert results[0]["score"] >= min_score

def test_ensure_extension(vector_store, mock_db):
    """Test pgvector extension initialization"""
    vector_store._ensure_extension()
    
    # Verify extension creation
    create_extension_call = mock_db.execute.call_args_list[0]
    sql = str(create_extension_call[0][0])
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    
    # Verify table creation
    create_table_call = mock_db.execute.call_args_list[1]
    sql = str(create_table_call[0][0])
    assert "CREATE TABLE IF NOT EXISTS document_embeddings" in sql
    assert "embedding vector" in sql
    assert "CREATE INDEX" in sql

@pytest.mark.asyncio
async def test_get_embedding(vector_store, mock_embeddings):
    """Test embedding generation"""
    text = "Test text for embedding"
    
    # Test with OpenAI-style embeddings
    embedding = await vector_store._get_embedding(text)
    assert isinstance(embedding, np.ndarray)
    assert embedding.dtype == np.float32
    
    # Test with HuggingFace-style embeddings
    mock_embeddings.embed_query = None
    mock_embeddings.encode.return_value = np.random.rand(384)
    
    embedding = await vector_store._get_embedding(text)
    assert isinstance(embedding, np.ndarray)
    assert embedding.dtype == np.float32

def test_clear(vector_store, mock_db):
    """Test clearing vector store"""
    # Test clearing all
    vector_store.clear()
    call_args = mock_db.execute.call_args
    sql = str(call_args[0][0])
    assert "DELETE FROM document_embeddings" in sql
    assert "WHERE" not in sql
    
    # Test clearing by fund_id
    vector_store.clear(fund_id=1)
    call_args = mock_db.execute.call_args
    sql = str(call_args[0][0])
    assert "DELETE FROM document_embeddings" in sql
    assert "WHERE fund_id = :fund_id" in sql

@pytest.mark.asyncio
async def test_error_handling(vector_store, mock_db):
    """Test error handling"""
    # Test add_document error
    mock_db.execute.side_effect = Exception("Database error")
    
    with pytest.raises(Exception):
        await vector_store.add_document(
            content="test",
            metadata={"document_id": 1}
        )
    
    assert mock_db.rollback.called
    
    # Test similarity_search error
    results = await vector_store.similarity_search("test query")
    assert len(results) == 0  # Should return empty list on error