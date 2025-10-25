"""
Enhanced table parser with validation and classification
"""
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Optional, Tuple, Any

class TableParser:
    """Parser for fund transaction tables with validation"""

    def __init__(self):
        # Column validation rules
        self.required_columns = {
            'capital_call': ['date', 'amount', 'description'],
            'distribution': ['date', 'amount', 'type'],
            'adjustment': ['date', 'amount', 'reason']
        }
        
        # Value validation patterns
        self.patterns = {
            'date': r'^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$|^\d{4}[-/]\d{1,2}[-/]\d{1,2}$',
            'amount': r'^\$?\s*\d+(?:,\d{3})*(?:\.\d{2})?$',
            'percentage': r'^\d+(?:\.\d+)?%$'
        }
        
        # Column name variations
        self.column_aliases = {
            'date': ['date', 'effective_date', 'transaction_date', 'due_date'],
            'amount': ['amount', 'value', 'total', 'commitment'],
            'type': ['type', 'category', 'transaction_type'],
            'description': ['description', 'details', 'notes'],
            'reason': ['reason', 'explanation', 'rationale']
        }
        
        # Keywords for classification
        self.keywords = {
            'capital_call': [
                'call', 'drawdown', 'contribution', 'commitment',
                'invest', 'funding', 'subscription'
            ],
            'distribution': [
                'distribution', 'return', 'dividend', 'proceeds',
                'payout', 'withdrawal', 'redemption', 'income'
            ],
            'adjustment': [
                'adjustment', 'correction', 'revision', 'update',
                'modify', 'amend', 'restate'
            ]
        }
        
        # Date formats to try
        self.date_formats = [
            "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d",
            "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%d-%B-%Y"
        ]

    def normalize_column_name(self, col: str) -> str:
        """Normalize column name using aliases"""
        col = col.lower().strip().replace(' ', '_')
        for std_name, aliases in self.column_aliases.items():
            if col in aliases:
                return std_name
        return col

    def validate_table_structure(self, table: List[List[str]]) -> bool:
        """Validate basic table structure"""
        if not table or len(table) < 2:  # Need header + data
            return False
            
        header = table[0]
        if not header or not any(header):  # Empty header
            return False
            
        width = len(header)
        if width < 2:  # Too few columns
            return False
            
        return all(len(row) == width for row in table[1:])

    def parse(self, table: List[List[Optional[str]]]) -> List[Dict]:
        """Parse and validate table data"""
        if not self.validate_table_structure(table):
            raise ValueError("Invalid table structure")
            
        # Normalize header
        header = [
            self.normalize_column_name(col)
            for col in table[0] if col
        ]
        
        # Process rows
        rows = []
        for row_idx, row in enumerate(table[1:], start=2):
            if len(row) != len(header):
                continue
                
            # Create dict with normalized values
            try:
                row_data = {}
                for col, value in zip(header, row):
                    if not value:
                        continue
                        
                    cleaned = value.strip()
                    if not cleaned:
                        continue
                        
                    # Parse dates
                    if col in ['date']:
                        date_value = self._parse_date(cleaned)
                        if date_value:
                            row_data[col] = date_value
                            
                    # Parse amounts    
                    elif col in ['amount']:
                        amount = self._parse_amount(cleaned)
                        if amount is not None:
                            row_data[col] = amount
                            
                    else:
                        row_data[col] = cleaned
                        
                if row_data:
                    row_data['row_number'] = row_idx
                    rows.append(row_data)
                    
            except (ValueError, InvalidOperation):
                continue
                
        return rows
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string using multiple formats"""
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
    
    def classify(self, parsed_data: Dict) -> Tuple[str, float]:
        """
        Classify table type with confidence score
        
        Returns:
            Tuple of (table_type, confidence_score)
        """
        scores = {
            'capital_call': 0.0,
            'distribution': 0.0, 
            'adjustment': 0.0
        }
        
        # Convert all values to string and lowercase
        text_content = ' '.join([
            str(v).lower() for v in parsed_data.values() if v
        ])
        
        # Score based on keywords
        for table_type, keywords in self.keywords.items():
            type_score = 0
            for keyword in keywords:
                if keyword in text_content:
                    type_score += 1
            if type_score > 0:
                scores[table_type] = type_score / len(keywords)
                
        # Adjust scores based on required columns
        for table_type, required_cols in self.required_columns.items():
            has_required = all(
                any(col in parsed_data for col in self.column_aliases[req])
                for req in required_cols
            )
            if has_required:
                scores[table_type] += 0.3
            else:
                scores[table_type] -= 0.2
                
        # Get highest scoring type
        max_score = max(scores.values())
        if max_score <= 0:
            return 'unknown', 0.0
            
        table_type = max(scores.items(), key=lambda x: x[1])[0]
        confidence = min(1.0, scores[table_type])
        
        return table_type, confidence

    def validate_parsed_data(
        self,
        parsed_data: Dict,
        table_type: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate parsed data against requirements
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        # Check required columns
        if table_type in self.required_columns:
            missing = []
            for req_col in self.required_columns[table_type]:
                if not any(col in parsed_data for col in self.column_aliases[req_col]):
                    missing.append(req_col)
                    
            if missing:
                errors.append(f"Missing required columns: {', '.join(missing)}")
                
        # Validate date format
        date_cols = [
            col for col in parsed_data.keys()
            if any(alias in col for alias in self.column_aliases['date'])
        ]
        for col in date_cols:
            value = str(parsed_data[col])
            if not re.match(self.patterns['date'], value):
                errors.append(f"Invalid date format in column {col}: {value}")
                
        # Validate amount format
        amount_cols = [
            col for col in parsed_data.keys()
            if any(alias in col for alias in self.column_aliases['amount'])
        ]
        for col in amount_cols:
            value = str(parsed_data[col])
            if not re.match(self.patterns['amount'], value):
                errors.append(f"Invalid amount format in column {col}: {value}")
                
        return not bool(errors), errors