import re
import string
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Dict, Tuple, Any
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.transaction import Adjustment, Distribution

class TableParser:
    """Parser for fund transaction tables with intelligent classification and validation"""

    def __init__(self):
        # Keywords for table classification
        self.classification_keywords = {
            'capital_call': ['call', 'commitment', 'drawdown', 'contribution'],
            'distribution': ['distribution', 'return', 'income', 'proceeds', 'dividend'],
            'adjustment': ['adjustment', 'correction', 'revised', 'update']
        }
        
        # Common date formats in fund documents
        self.date_formats = [
            "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d",
            "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%d-%B-%Y"
        ]

    def parse(self, table: List[List[Optional[str]]]) -> List[Dict[str, Any]]:
        """
        Parse table data with data cleaning and validation
        
        Args:
            table: Raw table data from PDF
            
        Returns:
            List of cleaned and validated row dictionaries
        """
        if not table or len(table) < 2:  # Require at least header + 1 row
            return []
            
        header = self._clean_header(table[0])
        if not header:
            return []
            
        rows = []
        for row_idx, row in enumerate(table[1:], start=2):
            if len(row) != len(header):
                continue  # Skip malformed rows
                
            try:
                cleaned_row = self._clean_row(dict(zip(header, row)))
                if cleaned_row:  # Only add valid rows
                    cleaned_row['row_number'] = row_idx  # For error tracking
                    rows.append(cleaned_row)
            except (ValueError, InvalidOperation) as e:
                continue  # Skip rows with validation errors
                
        return rows

    def _clean_header(self, header: List[Optional[str]]) -> List[str]:
        """Clean and normalize header names"""
        if not header:
            return []
            
        cleaned = []
        for col in header:
            if not col:
                continue
            # Normalize column names
            name = col.lower()
            name = re.sub(r'[^\w\s]', '', name)
            name = name.strip()
            name = re.sub(r'\s+', '_', name)
            cleaned.append(name)
            
        return cleaned

    def _clean_row(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Clean and validate row data"""
        cleaned = {}
        
        for key, value in row.items():
            if not value or value.strip() == '':
                continue
                
            cleaned_value = value.strip()
            
            # Handle date fields
            if any(x in key.lower() for x in ['date', 'effective', 'due']):
                cleaned_value = self._parse_date(cleaned_value)
                
            # Handle amount fields    
            elif any(x in key.lower() for x in ['amount', 'value', 'total', 'balance']):
                cleaned_value = self._parse_amount(cleaned_value)
                
            cleaned[key] = cleaned_value
            
        return cleaned if cleaned else None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime"""
        for fmt in self.date_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse and validate monetary amount"""
        # Remove currency symbols and commas
        cleaned = re.sub(r'[,$€£]', '', amount_str)
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None

    def classify(self, parsed_data: Dict[str, Any]) -> Tuple[str, float]:
        """
        Classify table type with confidence score
        
        Args:
            parsed_data: Cleaned row data
            
        Returns:
            Tuple of (table_type, confidence_score)
        """
        scores = {
            'capital_call': 0.0,
            'distribution': 0.0,
            'adjustment': 0.0
        }
        
        # Check headers and content
        text_to_check = ' '.join([
            *[str(k).lower() for k in parsed_data.keys()],
            *[str(v).lower() for v in parsed_data.values()]
        ])
        
        # Calculate scores
        for table_type, keywords in self.classification_keywords.items():
            for keyword in keywords:
                if keyword in text_to_check:
                    scores[table_type] += 1.0
                    
        # Normalize scores
        max_score = max(scores.values())
        if max_score == 0:
            return 'unknown', 0.0
            
        # Get type with highest score
        table_type = max(scores.items(), key=lambda x: x[1])[0]
        confidence = scores[table_type] / max_score
        
        return table_type, confidence