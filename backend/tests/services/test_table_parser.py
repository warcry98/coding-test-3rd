"""
Tests for the TableParser component
"""
import pytest
from datetime import datetime
from decimal import Decimal
from app.services.table_parser import TableParser

@pytest.fixture
def table_parser():
    """Create TableParser instance for tests"""
    return TableParser()

def test_normalize_column_name(table_parser):
    """Test column name normalization"""
    test_cases = [
        ("Transaction Date", "date"),
        ("Amount ($)", "amount"),
        ("Call Description", "description"),
        ("Return Type", "type"),
        ("Adjustment Reason", "reason")
    ]
    
    for input_name, expected in test_cases:
        assert table_parser.normalize_column_name(input_name) == expected

def test_validate_table_structure(table_parser):
    """Test table structure validation"""
    # Valid table
    valid_table = [
        ["Date", "Amount", "Description"],
        ["2024-01-01", "1000", "First call"],
        ["2024-02-01", "2000", "Second call"]
    ]
    assert table_parser.validate_table_structure(valid_table) is True
    
    # Invalid tables
    invalid_cases = [
        [],  # Empty table
        [[]],  # Empty header
        [["Date"]],  # Header only
        [["Date", "Amount"], ["2024-01-01"]],  # Row length mismatch
    ]
    
    for invalid_table in invalid_cases:
        assert table_parser.validate_table_structure(invalid_table) is False

def test_parse_valid_table(table_parser):
    """Test parsing valid table data"""
    table = [
        ["Date", "Amount", "Description"],
        ["2024-01-01", "$1,000.00", "First call"],
        ["2024-02-01", "$2,000.00", "Second call"]
    ]
    
    result = table_parser.parse(table)
    assert len(result) == 2
    
    # Check first row
    assert result[0]["date"] == datetime(2024, 1, 1)
    assert result[0]["amount"] == Decimal("1000.00")
    assert result[0]["description"] == "First call"

def test_parse_invalid_data(table_parser):
    """Test parsing invalid data handling"""
    table = [
        ["Date", "Amount", "Description"],
        ["invalid date", "not money", "Description"],
        ["2024-01-01", "$1,000.00", "Valid row"]
    ]
    
    result = table_parser.parse(table)
    assert len(result) == 1  # Only valid row should be parsed
    assert result[0]["description"] == "Valid row"

def test_classify_capital_call(table_parser):
    """Test capital call classification"""
    data = {
        "date": "2024-01-01",
        "amount": "$1,000.00",
        "description": "Capital Call for Investment"
    }
    
    table_type, confidence = table_parser.classify(data)
    assert table_type == "capital_call"
    assert confidence > 0.7

def test_classify_distribution(table_parser):
    """Test distribution classification"""
    data = {
        "date": "2024-01-01",
        "amount": "$1,000.00",
        "type": "Dividend Distribution"
    }
    
    table_type, confidence = table_parser.classify(data)
    assert table_type == "distribution"
    assert confidence > 0.7

def test_classify_adjustment(table_parser):
    """Test adjustment classification"""
    data = {
        "date": "2024-01-01",
        "amount": "$1,000.00",
        "reason": "Correction to previous call"
    }
    
    table_type, confidence = table_parser.classify(data)
    assert table_type == "adjustment"
    assert confidence > 0.7

def test_validate_parsed_data(table_parser):
    """Test data validation"""
    # Valid capital call
    valid_data = {
        "date": "2024-01-01",
        "amount": "$1,000.00",
        "description": "First call"
    }
    is_valid, errors = table_parser.validate_parsed_data(valid_data, "capital_call")
    assert is_valid is True
    assert not errors
    
    # Invalid data (missing required fields)
    invalid_data = {
        "date": "2024-01-01",
        "description": "Missing amount"
    }
    is_valid, errors = table_parser.validate_parsed_data(invalid_data, "capital_call")
    assert is_valid is False
    assert "amount" in str(errors)

def test_parse_date_formats(table_parser):
    """Test date parsing with different formats"""
    test_cases = [
        ("2024-01-01", datetime(2024, 1, 1)),
        ("01/01/2024", datetime(2024, 1, 1)),
        ("Jan 1, 2024", datetime(2024, 1, 1)),
        ("1-Jan-2024", datetime(2024, 1, 1))
    ]
    
    for date_str, expected in test_cases:
        result = table_parser._parse_date(date_str)
        assert result == expected

def test_parse_amount_formats(table_parser):
    """Test amount parsing with different formats"""
    test_cases = [
        ("$1,000.00", Decimal("1000.00")),
        ("1000.00", Decimal("1000.00")),
        ("$1,000", Decimal("1000")),
        ("1,000,000.50", Decimal("1000000.50"))
    ]
    
    for amount_str, expected in test_cases:
        result = table_parser._parse_amount(amount_str)
        assert result == expected