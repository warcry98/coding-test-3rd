"""
Application configuration
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""
    
    # Project
    PROJECT_NAME: str = "Fund Performance Analysis System"
    VERSION: str = "1.0.0"
    
    # API
    API_V1_STR: str = "/api"
    
    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://192.168.2.217:3000",
    ]
    
    # Database
    DATABASE_URL: str = "postgresql://funduser:fundpass@localhost:5432/funddb"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    
    # Anthropic (optional)
    ANTHROPIC_API_KEY: str = ""
    
    # Vector Store
    VECTOR_STORE_PATH: str = "./vector_store"
    FAISS_INDEX_PATH: str = "./faiss_index"
    
    # File Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    
    # Document Processing
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    # RAG
    TOP_K_RESULTS: int = 5
    SIMILARITY_THRESHOLD: float = 0.7

    # llama.cpp models
    EMBEDDING_MODEL: str = ""
    RAG_MODEL: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
