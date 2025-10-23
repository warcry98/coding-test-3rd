import re
import string
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from app.models.document import Document
from app.models.transaction import Adjustment, Distribution 

class TableParser:
    def __init__(self):
        pass

    def parse(self, table: List[List[Optional[str]]]) -> List:
        header = table[0]
        rows = [dict(zip(header, row)) for row in table[1:] if len(row) == len(header)]
        return rows
    
    def classify(self, parsed_data: Dict) -> str:
        headers = [h.lower() for h in parsed_data.keys()]
        content = [c.lower() for c in parsed_data.values()]

        if any("call" in c for c in content):
            return "capital_call"
        elif any("return" in c for c in content) or any("income" in c for c in content):
            return "distribution"
        elif any("adjustment" in c for c in content) or any("distribution" in c for c in content):
            return "adjustment"
        return "unknown"