"""
Document processing service using pdfplumber

TODO: Implement the document processing pipeline
- Extract tables from PDF using pdfplumber
- Classify tables (capital calls, distributions, adjustments)
- Extract and chunk text for vector storage
- Handle errors and edge cases
"""
from typing import Dict, List, Any
import logging
import re
import pdfplumber
from app.core.config import settings
from app.services.table_parser import TableParser
from app.models.document import Document
from app.models.fund import Fund

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Process PDF documents and extract structured data"""
    
    def __init__(self):
        self.table_parser = TableParser()
    
    async def process_document(self, file_path: str, document_id: int, fund_id: int) -> Dict[str, Any]:
        """
        Process a PDF document
        
        TODO: Implement this method
        - Open PDF with pdfplumber ✅
        - Extract tables from each page ✅
        - Parse and classify tables using TableParser ✅
        - Extract text and create chunks ✅
        - Store chunks in vector database
        - Return processing statistics
        
        Args:
            file_path: Path to the PDF file
            document_id: Database document ID
            fund_id: Fund ID
            
        Returns:
            Processing result with statistics
        """

        result = {
            "status": "pending",
            "error": "",
            "document_id": document_id,
            "fund_id": fund_id,
            "page_processed": 0,
            "tables_extracted": 0,
            "text_chunks": 0,
        }

        try:
            all_text_block = []

            with pdfplumber.open(file_path) as pdf:
                parsed_tables = self.table_parser.parse(pdf.pages, fund_id, document_id)
                for table in parsed_tables["tables"]:
                    self.table_parser.classify(table, fund_id)
                    result["tables_extracted"] += 1

                for page_idx, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    if text.strip():
                        all_text_block.append({
                            "page": page_idx,
                            "content": text.strip(),
                        })
                    
                    result["page_processed"] += 1
            
            chunks = self._chunk_text(all_text_block)
            result["text_chunks"] = len(chunks)

            print(chunks)

            result["status"] = "completed"
            logger.info(f"✅ Document {document_id} processed successfully")

        except Exception as e:
            logger.exception(f"Error processing document {document_id}: {e}")
            result.update({
                "status": "failed",
                "error": str(e)
            })

        return result
    
    def _chunk_text(self, text_content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Chunk text content for vector storage
        
        TODO: Implement intelligent text chunking
        - Split text into semantic chunks
        - Maintain context overlap
        - Preserve sentence boundaries
        - Add metadata to each chunk
        
        Args:
            text_content: List of text content with metadata
            
        Returns:
            List of text chunks with metadata
        """
        chunks = []

        for block in text_content:
            page = block.get("page")
            content = block.get("content", "").strip()
            if not content:
                continue

            raw_chunk = re.split(f'\n{2,}|(?<=[.!?])\s{2,}', content)

            for i, chunk_text in enumerate(raw_chunk, start=1):
                cleaned = chunk_text.strip()
                if not cleaned:
                    continue

                chunks.append({
                    "page": page,
                    "chunk_index": i,
                    "content": cleaned,
                    "metadata": {
                        "source": f"page_{page}",
                        "chunk_no": i,
                        "char_length": len(cleaned),
                    }
                })

        return chunks