"""
Query engine service for intelligent question answering

Implements:
- Intent classification
- Context retrieval
- Answer generation
- Source citation
"""
from typing import Dict, List, Any, Optional
import logging
import json
import re
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_community.llms import Ollama
from langchain.prompts import ChatPromptTemplate

from app.core.config import settings
from app.services.vector_store import VectorStore
from app.services.metrics_calculator import MetricsCalculator
from app.services.rag_engine import RAGEngine

logger = logging.getLogger(__name__)

class QueryEngine:
    """Query engine for fund analysis with intent classification"""
    
    def __init__(self):
        self.rag_engine = RAGEngine()
        
        # Intent classification patterns
        self.intent_patterns = {
            'calculation': [
                r'calculate', r'compute', r'what is the', r'total', 
                r'average', r'dpi', r'irr', r'roi', r'return', 
                r'performance', r'ratio'
            ],
            'definition': [
                r'what (does|is|are)', r'define', r'explain', r'mean',
                r'definition', r'describe', r'how (does|do)', r'why is'
            ],
            'comparison': [
                r'compare', r'difference between', r'versus', r'vs',
                r'better', r'worse', r'higher', r'lower'
            ],
            'time_series': [
                r'over time', r'trend', r'historical', r'year by year',
                r'quarterly', r'monthly', r'timeline'
            ]
        }
    
    async def process_query(
        self,
        query: str,
        fund_id: Optional[int] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Process user query with intent classification
        
        Features:
        - Query intent detection
        - Context retrieval
        - Answer generation
        - Source citation
        - Error handling
        
        Args:
            query: User question
            fund_id: Optional fund ID for context
            conversation_history: Previous conversation
            
        Returns:
            Answer with sources and metrics
        """
        start_time = datetime.now()
        
        try:
            # Step 1: Classify query intent
            intent = self._classify_intent(query)
            logger.info(f"Query intent: {intent}")
            
            # Step 2: Process with RAG
            response = await self.rag_engine.process_query(
                query=query,
                fund_id=fund_id,
                conversation_history=conversation_history
            )
            
            # Step 3: Enrich response
            response.update({
                "query_intent": intent,
                "processing_time": (datetime.now() - start_time).total_seconds()
            })
            
            if fund_id:
                response["fund_id"] = fund_id
            
            return response
            
        except Exception as e:
            logger.exception("Error processing query")
            return {
                "error": str(e),
                "answer": "I encountered an error while processing your query. Please try again.",
                "sources": [],
                "metrics": None,
                "processing_time": 0
            }
    
    def _classify_intent(self, query: str) -> str:
        """Classify query intent using regex patterns"""
        query_lower = query.lower()
        scores = {}
        
        for intent, patterns in self.intent_patterns.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    score += 1
            if score > 0:
                scores[intent] = score
                
        if not scores:
            return "general"
            
        return max(scores.items(), key=lambda x: x[1])[0]