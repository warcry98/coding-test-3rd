"""
Document processor service with intelligent chunking and extraction
"""
import re
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

import pdfplumber

from app.core.config import settings
from app.services.table_parser import TableParser
from app.services.vector_store import VectorStore
from app.models.transaction import CapitalCall, Distribution, Adjustment

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Process PDF documents with intelligent data extraction and validation"""
    
    def __init__(self):
        self.table_parser = TableParser()
        self.vector_store = VectorStore()
        
        # Text chunking config
        self.min_chunk_size = settings.MIN_CHUNK_SIZE
        self.max_chunk_size = settings.MAX_CHUNK_SIZE
        self.overlap_size = settings.CHUNK_OVERLAP
        
        # PDF processing settings
        self.table_confidence_threshold = settings.TABLE_CONFIDENCE_THRESHOLD
        self.pdf_table_settings = settings.PDF_TABLE_SETTINGS
        
        # Track statistics
        self.stats = {
            'tables_processed': 0,
            'tables_valid': 0,
            'tables_invalid': 0,
            'text_chunks': 0,
            'embedding_errors': 0
        }
    
    async def process_document(
            self, 
            file_path: str, 
            document_id: int, 
            fund_id: int
    ) -> Dict[str, Any]:
        """
        Process a PDF document with comprehensive error handling
        
        Features:
        - Table detection and classification
        - Data validation and cleaning
        - Text chunking and vectorization
        - Error handling and recovery
        
        Args:
            file_path: Path to PDF file
            document_id: Database document ID
            fund_id: Associated fund ID
            
        Returns:
            Processing results and statistics
        """
        # Reset statistics
        self.stats = {k: 0 for k in self.stats}
        start_time = datetime.now()
        
        result = {
            "status": "pending",
            "error": "",
            "document_id": document_id,
            "fund_id": fund_id,
            "page_processed": 0,
            "tables_extracted": 0,
            "text_chunks": 0,
            "parsed_tables": [],
            "invalid_tables": [],
            "warnings": []
        }

        try:
            all_text_blocks = []
            classified_tables = []

            # Process PDF
            with pdfplumber.open(file_path) as pdf:
                for page_idx, page in enumerate(pdf.pages, start=1):
                    logger.info(f"Processing page {page_idx}/{len(pdf.pages)}")
                    
                    # Extract and process tables
                    tables = page.extract_tables(
                        table_settings=self.pdf_table_settings
                    )
                    
                    for table_idx, table in enumerate(tables, start=1):
                        try:
                            # Parse and validate table
                            parsed_rows = self.table_parser.parse(table)
                            
                            for parsed_data in parsed_rows:
                                # Classify with confidence score
                                table_type, confidence = self.table_parser.classify(parsed_data)
                                
                                if confidence >= self.table_confidence_threshold:
                                    # Validate parsed data
                                    is_valid, errors = self.table_parser.validate_parsed_data(
                                        parsed_data, table_type
                                    )
                                    
                                    if is_valid:
                                        classified_tables.append({
                                            "page": page_idx,
                                            "table_index": table_idx,
                                            "type": table_type,
                                            "confidence": confidence,
                                            "data": parsed_data
                                        })
                                        self.stats['tables_valid'] += 1
                                    else:
                                        result["invalid_tables"].append({
                                            "page": page_idx,
                                            "table_index": table_idx,
                                            "errors": errors,
                                            "data": parsed_data
                                        })
                                        self.stats['tables_invalid'] += 1
                                else:
                                    result["warnings"].append(
                                        f"Low confidence table classification on page {page_idx}"
                                    )
                                    
                            result["tables_extracted"] += 1
                            self.stats['tables_processed'] += 1
                            
                        except Exception as e:
                            logger.error(f"Error processing table: {e}")
                            result["warnings"].append(
                                f"Failed to process table on page {page_idx}: {str(e)}"
                            )
                            continue

                    # Extract text content
                    text = page.extract_text() or ""
                    if text.strip():
                        all_text_blocks.append({
                            "page": page_idx,
                            "content": text.strip()
                        })
                    
                    result["page_processed"] += 1
                    
            # Process text blocks
            chunks = self._chunk_text(all_text_blocks)
            result["text_chunks"] = len(chunks)
            self.stats['text_chunks'] = len(chunks)
            
            # Store chunks in vector database
            try:
                for chunk in chunks:
                    await self.vector_store.add_document(
                        content=chunk["content"],
                        metadata={
                            "document_id": document_id,
                            "fund_id": fund_id,
                            **chunk["metadata"]
                        }
                    )
            except Exception as e:
                logger.error(f"Error storing vectors: {e}")
                self.stats['embedding_errors'] += 1
                result["warnings"].append(f"Vector storage error: {str(e)}")

            processing_time = (datetime.now() - start_time).total_seconds()
            result.update({
                "status": "completed",
                "processing_time": round(processing_time, 2),
                "tables_found": len(classified_tables),
                "invalid_tables": len(result["invalid_tables"]),
                "stats": self.stats
            })
            
            logger.info(f"✅ Document {document_id} processed successfully")

        except Exception as e:
            logger.exception(f"Error processing document {document_id}")
            result.update({
                "status": "failed",
                "error": str(e),
                "stats": self.stats
            })

        return result
    
    def _chunk_text(self, text_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Chunk text using intelligent semantic splitting
        
        Features:
        - Semantic boundary preservation
        - Sentence overlap for context
        - Length normalization
        - Metadata enrichment
        
        Args:
            text_blocks: List of text blocks with metadata
            
        Returns:
            List of text chunks with metadata
        """
        chunks = []
        
        for block in text_blocks:
            page = block.get("page")
            content = block.get("content", "").strip()
            
            if not content:
                continue
                
            # Step 1: Split into paragraphs
            paragraphs = re.split(r'\n{2,}', content)
            
            for para_idx, para in enumerate(paragraphs):
                if not para.strip():
                    continue
                    
                # Step 2: Split into sentences
                sentences = re.split(r'(?<=[.!?])\s+', para)
                current_chunk = []
                current_length = 0
                
                for sent_idx, sentence in enumerate(sentences):
                    sent_length = len(sentence)
                    
                    # Check if adding sentence exceeds max size
                    if current_length + sent_length > self.max_chunk_size and current_chunk:
                        # Save current chunk
                        chunk_text = ' '.join(current_chunk)
                        if len(chunk_text) >= self.min_chunk_size:
                            chunks.append(self._create_chunk_metadata(
                                text=chunk_text,
                                page=page,
                                para_idx=para_idx,
                                chunk_idx=len(chunks)
                            ))
                        
                        # Start new chunk with overlap
                        overlap_point = max(0, len(current_chunk) - 2)
                        current_chunk = current_chunk[overlap_point:]
                        current_length = sum(len(s) for s in current_chunk)
                    
                    current_chunk.append(sentence)
                    current_length += sent_length
                
                # Handle remaining sentences
                if current_chunk:
                    chunk_text = ' '.join(current_chunk)
                    if len(chunk_text) >= self.min_chunk_size:
                        chunks.append(self._create_chunk_metadata(
                            text=chunk_text,
                            page=page,
                            para_idx=para_idx,
                            chunk_idx=len(chunks)
                        ))
        
        return chunks
        
    def _create_chunk_metadata(
        self,
        text: str,
        page: int,
        para_idx: int,
        chunk_idx: int
    ) -> Dict[str, Any]:
        """Create metadata for text chunk"""
        return {
            "content": text.strip(),
            "metadata": {
                "page": page,
                "paragraph": para_idx,
                "chunk_index": chunk_idx,
                "char_length": len(text),
                "word_count": len(text.split()),
                "created_at": datetime.utcnow().isoformat()
            }
        }