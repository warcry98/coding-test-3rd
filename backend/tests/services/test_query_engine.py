"""
Tests for the RAG Query Engine component
"""
import pytest
from unittest.mock import Mock, patch
from typing import Dict, List, Any

from app.services.query_engine import QueryEngine
from app.services.vector_store import VectorStore
from app.services.metrics_calculator import MetricsCalculator

@pytest.fixture
def mock_rag_engine():
    """Mock RAG engine"""
    mock = Mock()
    mock.process_query.return_value = {
        "answer": "Test answer",
        "sources": [{"content": "source 1"}],
        "metrics": None
    }
    return mock

@pytest.fixture
def query_engine(mock_rag_engine):
    """Create QueryEngine with mocked dependencies"""
    engine = QueryEngine()
    engine.rag_engine = mock_rag_engine
    return engine

@pytest.mark.asyncio
async def test_process_query_basic(query_engine):
    """Test basic query processing"""
    query = "What is the fund's DPI?"
    
    result = await query_engine.process_query(query)
    
    assert "answer" in result
    assert "sources" in result
    assert "processing_time" in result
    assert "query_intent" in result

@pytest.mark.asyncio
async def test_process_query_with_fund_id(query_engine):
    """Test query processing with fund context"""
    query = "Calculate the IRR"
    fund_id = 1
    
    result = await query_engine.process_query(
        query=query,
        fund_id=fund_id
    )
    
    assert result["fund_id"] == fund_id
    assert query_engine.rag_engine.process_query.called_with(
        query=query,
        fund_id=fund_id
    )

@pytest.mark.asyncio
async def test_process_query_with_history(query_engine):
    """Test query processing with conversation history"""
    query = "What about last year?"
    history = [
        {"role": "user", "content": "What is the current DPI?"},
        {"role": "assistant", "content": "The current DPI is 1.5"}
    ]
    
    result = await query_engine.process_query(
        query=query,
        conversation_history=history
    )
    
    assert query_engine.rag_engine.process_query.called_with(
        query=query,
        conversation_history=history
    )

def test_classify_intent_calculation(query_engine):
    """Test calculation intent classification"""
    calculation_queries = [
        "What is the DPI?",
        "Calculate the IRR",
        "What's the total return?",
        "Show me the performance metrics"
    ]
    
    for query in calculation_queries:
        intent = query_engine._classify_intent(query)
        assert intent == "calculation"

def test_classify_intent_definition(query_engine):
    """Test definition intent classification"""
    definition_queries = [
        "What does DPI mean?",
        "Define IRR",
        "Explain how TVPI is calculated",
        "Why is DPI important?"
    ]
    
    for query in definition_queries:
        intent = query_engine._classify_intent(query)
        assert intent == "definition"

def test_classify_intent_comparison(query_engine):
    """Test comparison intent classification"""
    comparison_queries = [
        "Compare Fund A and Fund B",
        "What's the difference between DPI and TVPI?",
        "Which fund performed better?",
        "IRR vs MOIC"
    ]
    
    for query in comparison_queries:
        intent = query_engine._classify_intent(query)
        assert intent == "comparison"

def test_classify_intent_time_series(query_engine):
    """Test time series intent classification"""
    time_queries = [
        "Show DPI over time",
        "What's the quarterly performance?",
        "How has the fund performed historically?",
        "Show monthly returns"
    ]
    
    for query in time_queries:
        intent = query_engine._classify_intent(query)
        assert intent == "time_series"

def test_classify_intent_general(query_engine):
    """Test general intent classification"""
    general_queries = [
        "Hello",
        "Can you help me?",
        "Show me the documents",
        "List all funds"
    ]
    
    for query in general_queries:
        intent = query_engine._classify_intent(query)
        assert intent == "general"

@pytest.mark.asyncio
async def test_error_handling(query_engine):
    """Test error handling in query processing"""
    # Mock RAG engine to raise exception
    query_engine.rag_engine.process_query.side_effect = Exception("Test error")
    
    result = await query_engine.process_query("Test query")
    
    assert "error" in result
    assert result["answer"].startswith("I encountered an error")
    assert result["sources"] == []
    assert result["metrics"] is None
    assert result["processing_time"] == 0

@pytest.mark.asyncio
async def test_process_query_performance(query_engine):
    """Test query processing performance tracking"""
    query = "What is the fund's performance?"
    
    result = await query_engine.process_query(query)
    
    assert "processing_time" in result
    assert isinstance(result["processing_time"], (int, float))
    assert result["processing_time"] >= 0