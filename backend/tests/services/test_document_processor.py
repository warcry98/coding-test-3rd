"""
Tests for the Document Processor component
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from pathlib import Path

from app.services.document_processor import DocumentProcessor
from app.services.table_parser import TableParser
from app.services.vector_store import VectorStore

@pytest.fixture
def mock_vector_store():
    """Mock VectorStore for testing"""
    mock = Mock(spec=VectorStore)
    mock.add_document.return_value = None
    return mock

@pytest.fixture
def mock_table_parser():
    """Mock TableParser for testing"""
    mock = Mock(spec=TableParser)
    mock.parse.return_value = [{"date": "2024-01-01", "amount": "$1,000.00"}]
    mock.classify.return_value = ("capital_call", 0.9)
    mock.validate_parsed_data.return_value = (True, [])
    return mock

@pytest.fixture
def document_processor(mock_vector_store, mock_table_parser):
    """Create DocumentProcessor with mocked dependencies"""
    processor = DocumentProcessor()
    processor.vector_store = mock_vector_store
    processor.table_parser = mock_table_parser
    return processor

@pytest.fixture
def sample_pdf_path(tmp_path):
    """Create a temporary PDF file for testing"""
    pdf_path = tmp_path / "test.pdf"
    # TODO: Create a test PDF file
    return str(pdf_path)

@pytest.mark.asyncio
async def test_process_document_success(document_processor, sample_pdf_path):
    """Test successful document processing"""
    result = await document_processor.process_document(
        file_path=sample_pdf_path,
        document_id=1,
        fund_id=1
    )
    
    assert result["status"] == "completed"
    assert result["error"] == ""
    assert result["page_processed"] > 0
    assert result["tables_extracted"] > 0
    assert result["text_chunks"] > 0

@pytest.mark.asyncio
async def test_process_document_invalid_pdf(document_processor):
    """Test handling invalid PDF file"""
    result = await document_processor.process_document(
        file_path="nonexistent.pdf",
        document_id=1,
        fund_id=1
    )
    
    assert result["status"] == "failed"
    assert result["error"] != ""

def test_chunk_text(document_processor):
    """Test text chunking functionality"""
    text_blocks = [
        {
            "page": 1,
            "content": "This is a test paragraph. It has multiple sentences. "
                      "We want to test chunking. Here is more text."
        },
        {
            "page": 2,
            "content": "Another paragraph. With more sentences. "
                      "Testing chunk overlap. And boundaries."
        }
    ]
    
    chunks = document_processor._chunk_text(text_blocks)
    
    assert len(chunks) > 0
    for chunk in chunks:
        assert "content" in chunk
        assert "metadata" in chunk
        assert len(chunk["content"]) <= document_processor.max_chunk_size
        assert len(chunk["content"]) >= document_processor.min_chunk_size

def test_create_chunk_metadata(document_processor):
    """Test chunk metadata creation"""
    chunk = document_processor._create_chunk_metadata(
        text="Test chunk content",
        page=1,
        para_idx=0,
        chunk_idx=0
    )
    
    assert "content" in chunk
    assert "metadata" in chunk
    metadata = chunk["metadata"]
    assert metadata["page"] == 1
    assert metadata["paragraph"] == 0
    assert metadata["chunk_index"] == 0
    assert metadata["char_length"] > 0
    assert metadata["word_count"] > 0
    assert "created_at" in metadata

@pytest.mark.asyncio
async def test_table_processing(document_processor, mock_table_parser):
    """Test table processing and classification"""
    # Mock table data
    mock_table = [
        ["Date", "Amount", "Description"],
        ["2024-01-01", "$1,000.00", "First call"]
    ]
    
    mock_table_parser.parse.return_value = [{
        "date": "2024-01-01",
        "amount": "$1,000.00",
        "description": "First call"
    }]
    
    # Process table
    with patch('pdfplumber.open') as mock_pdf:
        mock_page = Mock()
        mock_page.extract_tables.return_value = [mock_table]
        mock_page.extract_text.return_value = "Sample text"
        mock_pdf.return_value.__enter__.return_value.pages = [mock_page]
        
        result = await document_processor.process_document(
            file_path="test.pdf",
            document_id=1,
            fund_id=1
        )
    
    assert result["tables_extracted"] > 0
    assert len(result["invalid_tables"]) == 0

@pytest.mark.asyncio
async def test_vector_storage_integration(document_processor, mock_vector_store):
    """Test vector storage integration"""
    text_blocks = [{
        "page": 1,
        "content": "Test content for vector storage"
    }]
    
    chunks = document_processor._chunk_text(text_blocks)
    
    # Process document with chunks
    with patch('pdfplumber.open') as mock_pdf:
        mock_page = Mock()
        mock_page.extract_tables.return_value = []
        mock_page.extract_text.return_value = text_blocks[0]["content"]
        mock_pdf.return_value.__enter__.return_value.pages = [mock_page]
        
        await document_processor.process_document(
            file_path="test.pdf",
            document_id=1,
            fund_id=1
        )
    
    # Verify vector store calls
    assert mock_vector_store.add_document.called
    call_args = mock_vector_store.add_document.call_args_list
    for args in call_args:
        _, kwargs = args
        assert "content" in kwargs
        assert "metadata" in kwargs
        assert kwargs["metadata"]["document_id"] == 1
        assert kwargs["metadata"]["fund_id"] == 1

@pytest.mark.asyncio
async def test_error_handling(document_processor):
    """Test error handling and reporting"""
    # Test with invalid file
    result = await document_processor.process_document(
        file_path="nonexistent.pdf",
        document_id=1,
        fund_id=1
    )
    
    assert result["status"] == "failed"
    assert result["error"] != ""
    assert "stats" in result
    
    # Test with corrupted table
    mock_table_parser = Mock(spec=TableParser)
    mock_table_parser.parse.side_effect = Exception("Table parsing error")
    document_processor.table_parser = mock_table_parser
    
    with patch('pdfplumber.open') as mock_pdf:
        mock_page = Mock()
        mock_page.extract_tables.return_value = [[["Invalid table"]]]
        mock_page.extract_text.return_value = "Sample text"
        mock_pdf.return_value.__enter__.return_value.pages = [mock_page]
        
        result = await document_processor.process_document(
            file_path="test.pdf",
            document_id=1,
            fund_id=1
        )
    
    assert "warnings" in result
    assert len(result["warnings"]) > 0
