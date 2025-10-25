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
    OPENAI_MODEL: str = ""
    OPENAI_EMBEDDING_MODEL: str = ""
    
    # Anthropic (optional)
    ANTHROPIC_API_KEY: str = ""

    # ollama
    LLM_PROVIDER: str = ""
    OLLAMA_BASE_URL: str = ""
    OLLAMA_MODEL: str = ""
    OLLAMA_EMBEDDING_MODEL: str = ""
    
    # Vector Store
    VECTOR_STORE_PATH: str = "./vector_store"
    FAISS_INDEX_PATH: str = "./faiss_index"
    
    # File Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    
    # Document Processing
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    MIN_CHUNK_SIZE: int = 100
    MAX_CHUNK_SIZE: int = 2000
    
    # PDF Processing
    TABLE_CONFIDENCE_THRESHOLD: float = 0.7
    PDF_TABLE_SETTINGS: dict = {
        'vertical_strategy': 'text',
        'horizontal_strategy': 'text',
        'intersection_x_tolerance': 2,
        'intersection_y_tolerance': 2,
        'snap_tolerance': 3,
        'join_tolerance': 3,
        'edge_min_length': 3
    }
    
    # RAG
    TOP_K_RESULTS: int = 5
    SIMILARITY_THRESHOLD: float = 0.7
    MIN_SIMILARITY_SCORE: float = 0.2
    MAX_CONTEXT_CHUNKS: int = 10
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
