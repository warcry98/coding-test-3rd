"""
Vector store service using pgvector (PostgreSQL extension)

TODO: Implement vector storage using pgvector
- Create embeddings table in PostgreSQL
- Store document chunks with vector embeddings
- Implement similarity search using pgvector operators
- Handle metadata filtering
"""
from typing import List, Dict, Any, Optional
import json
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings, OllamaEmbeddings
from app.core.config import settings
from app.db.session import SessionLocal


class VectorStore:
    """pgvector-based vector store for document embeddings"""
    
    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()
        self.embeddings = self._initialize_embeddings()
        self._ensure_extension()
    
    def _initialize_embeddings(self):
        """Initialize embedding model"""
        if settings.LLM_PROVIDER == "ollama":
            return OllamaEmbeddings(
                model=settings.OLLAMA_EMBEDDING_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
            )
        if settings.OPENAI_API_KEY:
            return OpenAIEmbeddings(
                model=settings.OPENAI_EMBEDDING_MODEL,
                openai_api_key=settings.OPENAI_API_KEY
            )
        else:
            # Fallback to local embeddings
            return HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )
    
    def _ensure_extension(self):
        """
        Ensure pgvector extension is enabled
        
        TODO: Implement this method
        - Execute: CREATE EXTENSION IF NOT EXISTS vector;
        - Create embeddings table if not exists
        """
        try:
            # Enable pgvector extension
            self.db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            
            # Create embeddings table
            # Dimension: 1536 for OpenAI, 384 for sentence-transformers
            dimension = 768 if settings.LLM_PROVIDER == "ollama" else 384
            
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS document_embeddings (
                id SERIAL PRIMARY KEY,
                document_id INTEGER,
                fund_id INTEGER,
                content TEXT NOT NULL,
                embedding vector({dimension}),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS document_embeddings_embedding_idx 
            ON document_embeddings USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100);
            """
            
            self.db.execute(text(create_table_sql))
            self.db.commit()
        except Exception as e:
            print(f"Error ensuring pgvector extension: {e}")
            self.db.rollback()
    
    async def add_document(self, content: str, metadata: Dict[str, Any]):
        """
        Add a document to the vector store
        
        TODO: Implement this method
        - Generate embedding for content
        - Insert into document_embeddings table
        - Store metadata as JSONB
        """
        try:
            # Generate embedding
            embedding = await self._get_embedding(content)
            embedding_list = embedding.tolist()
            
            # Insert into database
            insert_sql = text("""
                INSERT INTO document_embeddings (document_id, fund_id, content, embedding, metadata)
                VALUES (:document_id, :fund_id, :content, CAST(:embedding AS vector), CAST(:metadata AS jsonb))
            """)
            
            self.db.execute(insert_sql, {
                "document_id": metadata.get("document_id"),
                "fund_id": metadata.get("fund_id"),
                "content": content,
                "embedding": str(embedding_list),
                "metadata": json.dumps(metadata)
            })
            self.db.commit()
        except Exception as e:
            print(f"Error adding document: {e}")
            self.db.rollback()
            raise
    
    async def similarity_search(
        self, 
        query: str, 
        k: int = 5, 
        filter_metadata: Optional[Dict[str, Any]] = None,
        min_score: float = 0.2
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents with advanced filtering
        
        Features:
        - Cosine similarity search with pgvector
        - Metadata filtering
        - Score thresholding
        - JSON metadata handling
        - Error recovery
        
        Args:
            query: Search query text
            k: Number of results (default: 5)
            filter_metadata: Optional filters like {"fund_id": 1}
            min_score: Minimum similarity score (default: 0.2)
            
        Returns:
            List of matching documents with scores
        """
        try:
            # Generate query embedding
            query_embedding = await self._get_embedding(query)
            embedding_list = query_embedding.tolist()
            
            # Build metadata filters
            conditions = []
            params = {
                "query_embedding": str(embedding_list),
                "k": k,
                "min_score": min_score
            }
            
            if filter_metadata:
                for key, value in filter_metadata.items():
                    if key in ["document_id", "fund_id"]:
                        # Direct column filters
                        conditions.append(f"{key} = :{key}")
                        params[key] = value
                    else:
                        # JSON metadata filters
                        conditions.append(
                            f"metadata->:key = :value::jsonb"
                        )
                        params[f"key_{key}"] = key
                        params[f"value_{key}"] = json.dumps(value)
                        
            where_clause = "WHERE 1 - (embedding <=> CAST(:query_embedding AS vector)) >= :min_score"
            if conditions:
                where_clause += " AND " + " AND ".join(conditions)
            
            # Optimized similarity search query
            search_sql = text(f"""
                WITH ranked_results AS (
                    SELECT 
                        id,
                        document_id,
                        fund_id,
                        content,
                        metadata,
                        1 - (embedding <=> CAST(:query_embedding AS vector)) as similarity_score,
                        ROW_NUMBER() OVER (
                            ORDER BY embedding <=> CAST(:query_embedding AS vector)
                        ) as rank
                    FROM document_embeddings
                    {where_clause}
                )
                SELECT *
                FROM ranked_results
                WHERE rank <= :k
                ORDER BY similarity_score DESC
            """)
            
            result = self.db.execute(search_sql, {
                "query_embedding": str(embedding_list),
                "k": k,
                "min_score": min_score,
            })
            
            # Format results
            results = []
            for row in result:
                results.append({
                    "id": row[0],
                    "document_id": row[1],
                    "fund_id": row[2],
                    "content": row[3],
                    "metadata": row[4],
                    "score": float(row[5])
                })
            
            return results
        except Exception as e:
            print(f"Error in similarity search: {e}")
            return []
    
    async def _get_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for text"""
        if hasattr(self.embeddings, 'embed_query'):
            embedding = self.embeddings.embed_query(text)
        else:
            embedding = self.embeddings.encode(text)
        
        return np.array(embedding, dtype=np.float32)
    
    def clear(self, fund_id: Optional[int] = None):
        """
        Clear the vector store
        
        TODO: Implement this method
        - Delete all embeddings (or filter by fund_id)
        """
        try:
            if fund_id:
                delete_sql = text("DELETE FROM document_embeddings WHERE fund_id = :fund_id")
                self.db.execute(delete_sql, {"fund_id": fund_id})
            else:
                delete_sql = text("DELETE FROM document_embeddings")
                self.db.execute(delete_sql)
            
            self.db.commit()
        except Exception as e:
            print(f"Error clearing vector store: {e}")
            self.db.rollback()
