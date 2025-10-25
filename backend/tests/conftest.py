"""
Shared test fixtures and configuration
"""
import os
import pytest
import tempfile
import pdfplumber
from pathlib import Path
from unittest.mock import Mock
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.vector_store import VectorStore
from app.services.table_parser import TableParser
from app.services.document_processor import DocumentProcessor

@pytest.fixture
def test_db():
    """Create test database session"""
    mock = Mock(spec=Session)
    mock.execute.return_value = Mock()
    mock.commit.return_value = None
    return mock

@pytest.fixture
def sample_pdf():
    """Create a sample PDF file for testing"""
    pdf_content = """
    Fund Performance Report
    
    Capital Calls
    Date        Amount      Description
    2024-01-01  $1,000.00  Initial call
    2024-02-01  $2,000.00  Second call
    
    Distributions
    Date        Amount      Type
    2024-03-01  $500.00    Return of Capital
    2024-04-01  $1,500.00  Dividend
    
    Text content for testing extraction and chunking.
    This should be processed into semantic chunks.
    Multiple paragraphs help test the chunking logic.
    
    Another paragraph with different content.
    More text to ensure we have enough for testing.
    """
    
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
        f.write(pdf_content.encode('utf-8'))
        
    return Path(f.name)

@pytest.fixture
def clean_test_files():
    """Clean up test files after tests"""
    yield
    # Clean up created files
    test_files = Path(tempfile.gettempdir()).glob('test_*.pdf')
    for f in test_files:
        try:
            f.unlink()
        except:
            pass

@pytest.fixture
def mock_embeddings():
    """Mock embeddings model"""
    mock = Mock()
    mock.embed_query.return_value = [0.1] * 384  # Default dimension
    return mock

@pytest.fixture
def mock_vector_store(test_db, mock_embeddings):
    """Create VectorStore with mocked dependencies"""
    store = VectorStore(db=test_db)
    store.embeddings = mock_embeddings
    return store

@pytest.fixture
def mock_table_parser():
    """Create TableParser for testing"""
    return TableParser()

@pytest.fixture
def document_processor(mock_vector_store, mock_table_parser):
    """Create DocumentProcessor with test dependencies"""
    processor = DocumentProcessor()
    processor.vector_store = mock_vector_store
    processor.table_parser = mock_table_parser
    return processor

@pytest.fixture(autouse=True)
def test_settings():
    """Override settings for testing"""
    settings.CHUNK_SIZE = 500
    settings.CHUNK_OVERLAP = 50
    settings.MIN_CHUNK_SIZE = 100
    settings.MAX_CHUNK_SIZE = 1000
    settings.TABLE_CONFIDENCE_THRESHOLD = 0.7
    settings.TOP_K_RESULTS = 3
    return settings