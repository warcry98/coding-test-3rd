"""
Document processing service using pdfplumber

TODO: Implement the document processing pipeline
- Extract tables from PDF using pdfplumber
- Classify tables (capital calls, distributions, adjustments)
- Extract and chunk text for vector storage
- Handle errors and edge cases
"""
from typing import Dict, List, Any, Tuple
import logging
import re
import math
import pdfplumber
from app.core.config import settings
from app.services.table_parser import TableParser
from app.models.document import Document
from app.models.fund import Fund
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT_RE = re.compile(r"(?<!\b\w\.[A-Z]\.)"          # ignore "U.S."
                                r"(?<!\b[A-Z][a-z]\.)"         # ignore initials "A."
                                r"(?<!\bet al\.)"
                                r"(?<=[.!?])\s+(?=[A-Z(])")    # split on .!? followed by space + capital or "("

_BULLET_SPLIT_RE = re.compile(r"(?:\n|\r|\r\n)+(?=\s*[-•●◦∙*]\s+)")

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

            vector_store = VectorStore()
            for c in chunks:
                meta = {
                    "document_id": document_id,
                    "fund_id": fund_id,
                    "page": c["page"],
                    "chunk_index": c["chunk_index"],
                    **(c.get("metadata") or {})
                }
                await vector_store.add_document(content=c["content"], metadata=meta)

            result["status"] = "completed"
            logger.info(f"✅ Document {document_id} processed successfully")

        except Exception as e:
            logger.exception(f"Error processing document {document_id}: {e}")
            result.update({
                "status": "failed",
                "error": str(e)
            })

        return result
    
    
    def _chunk_text(
        self, 
        text_content: List[Dict[str, Any]], 
        max_tokens: int = 400, 
        overlap_tokens: int = 50
    ) -> List[Dict[str, Any]]:
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
        def estimate_tokens(text: str) -> int:
            """Rough token count (approx 4 chars/token if tiktoken not installed)."""
            try:
                import tiktoken
                enc = tiktoken.get_encoding("cl100k_base")
                return len(enc.encode(text))
            except Exception:
                return max(1, math.ceil(len(text) / 4))

        def split_sentences(text: str) -> List[str]:
            """Split text into sentences and remove empties."""
            parts = re.split(r'(?<=[.!?])\s+', text)
            return [p.strip() for p in parts if p.strip()]

        chunks = []

        for block in text_content:
            page = block.get("page")
            content = (block.get("content") or "").strip()
            if not content:
                continue

            sentences = split_sentences(content)
            buffer, buffer_tokens = [], 0
            chunk_index = 0

            for sentence in sentences:
                sent_tokens = estimate_tokens(sentence)

                # If adding this sentence would exceed max_tokens → flush current buffer
                if buffer_tokens + sent_tokens > max_tokens and buffer:
                    chunk_index += 1
                    chunk_text = " ".join(buffer).strip()
                    chunks.append({
                        "page": page,
                        "chunk_index": chunk_index,
                        "content": chunk_text,
                        "metadata": {
                            "source": f"page_{page}",
                            "chunk_no": chunk_index,
                            "char_length": len(chunk_text),
                        },
                    })

                    # keep small overlap from the end for context
                    if overlap_tokens > 0:
                        overlap = []
                        token_sum = 0
                        for s in reversed(buffer):
                            t = estimate_tokens(s)
                            token_sum += t
                            if token_sum > overlap_tokens:
                                break
                            overlap.insert(0, s)
                        buffer = overlap
                        buffer_tokens = sum(estimate_tokens(s) for s in buffer)
                    else:
                        buffer, buffer_tokens = [], 0

                buffer.append(sentence)
                buffer_tokens += sent_tokens

            # flush any remaining buffer
            if buffer:
                chunk_index += 1
                chunk_text = " ".join(buffer).strip()
                chunks.append({
                    "page": page,
                    "chunk_index": chunk_index,
                    "content": chunk_text,
                    "metadata": {
                        "source": f"page_{page}",
                        "chunk_no": chunk_index,
                        "char_length": len(chunk_text),
                    },
                })

        return chunks