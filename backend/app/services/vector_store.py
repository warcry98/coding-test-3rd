"""
Vector store service using pgvector (PostgreSQL extension)

TODO: Implement vector storage using pgvector
- Create embeddings table in PostgreSQL
- Store document chunks with vector embeddings
- Implement similarity search using pgvector operators
- Handle metadata filtering
"""
import json
from typing import List, Dict, Any, Optional
from llama_cpp import Llama
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import text
from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
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
        return Llama(model_path=settings.EMBEDDING_MODEL, n_ctx=2048, embedding=True, verbose=False)
    
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
            dimension = 384
            
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
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents using cosine similarity
        
        TODO: Implement this method
        - Generate query embedding
        - Use pgvector's <=> operator for cosine distance
        - Apply metadata filters if provided
        - Return top k results
        
        Args:
            query: Search query
            k: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {"fund_id": 1})
            
        Returns:
            List of similar documents with scores
        """
        try:
            # Generate query embedding
            print(query)
            query_embedding = await self._get_embedding(query)
            embedding_list = query_embedding.tolist()
            
            # Build query with optional filters
            where_clause = ""
            if filter_metadata:
                conditions = []
                for key, value in filter_metadata.items():
                    if key in ["document_id", "fund_id"]:
                        conditions.append(f"{key} = {value}")
                if conditions:
                    where_clause = "WHERE " + " AND ".join(conditions)
            
            # Search using cosine distance (<=> operator)
            search_sql = text(f"""
                SELECT 
                    id,
                    document_id,
                    fund_id,
                    content,
                    metadata,
                    1 - (embedding <=> CAST(:query_embedding AS vector)) as similarity_score
                FROM document_embeddings
                {where_clause}
                ORDER BY embedding <=> CAST(:query_embedding AS vector)
                LIMIT :k
            """)
            
            result = self.db.execute(search_sql, {
                "query_embedding": str(embedding_list),
                "k": k
            })

            print("result", result.all())
            
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
        prompt = f"query: {text.strip()}"

        embedding = self.embeddings.create_embedding(prompt)
        vec = np.array(embedding["data"][0]["embedding"], dtype=np.float32)

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        
        return vec
    
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
