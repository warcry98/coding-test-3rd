"""
RAG (Retrieval Augmented Generation) engine for fund analysis

Implements:
- Text chunking strategy
- Context retrieval
- Prompt management
- Response generation
"""
from typing import Dict, List, Any, Optional
import logging
import json
from datetime import datetime

from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_community.chat_models.ollama import ChatOllama
from langchain.prompts import ChatPromptTemplate

from app.core.config import settings
from app.services.vector_store import VectorStore
from app.services.metrics_calculator import MetricsCalculator

logger = logging.getLogger(__name__)

class RAGEngine:
    """RAG-based query processing for fund analysis"""
    
    def __init__(self):
        self.vector_store = VectorStore()
        self.metrics_calculator = MetricsCalculator()
        
        # Initialize LLM based on settings
        if settings.LLM_PROVIDER == "ollama":
            self.llm = ChatOllama(
                model=settings.OLLAMA_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
            )
        if settings.OPENAI_API_KEY:
            self.llm = ChatOpenAI(
                model=settings.OPENAI_MODEL,
                temperature=0.1,
                openai_api_key=settings.OPENAI_API_KEY
            )
        
        # Default system prompt
        self.system_prompt = """You are a fund analysis expert assistant. Your role is to:
1. Answer questions about fund performance metrics
2. Explain investment concepts
3. Retrieve historical transaction data
4. Help analyze fund documents

Use the provided context and metrics data in your responses.
Always cite your sources and explain your calculations."""

    async def process_query(
        self,
        query: str,
        fund_id: Optional[int] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Process a user query using RAG
        
        Args:
            query: User's question
            fund_id: Optional fund ID to scope search
            conversation_history: Previous messages for context
            
        Returns:
            Dict containing answer, sources, metrics and timing
        """
        start_time = datetime.now()
        
        try:
            # Step 1: Classify query intent
            intent = self._classify_intent(query)
            
            # Step 2: Retrieve relevant context
            filter_metadata = {"fund_id": fund_id} if fund_id else None
            relevant_docs = await self.vector_store.similarity_search(
                query=query,
                k=settings.TOP_K_RESULTS,
                filter_metadata=filter_metadata
            )
            
            # Step 3: Get relevant metrics if needed
            metrics = None
            if intent == "calculation" and fund_id:
                try:
                    metrics = self.metrics_calculator.calculate_all_metrics(fund_id)
                except Exception as e:
                    logger.error(f"Error calculating metrics: {e}")
            
            # Step 4: Build prompt with context
            prompt = self._build_prompt(
                query=query,
                context=relevant_docs,
                metrics=metrics,
                conversation_history=conversation_history
            )
            
            # Step 5: Generate response
            response = await self._generate_response(prompt)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return {
                "answer": response,
                "sources": [
                    {
                        "content": doc["content"],
                        "metadata": doc.get("metadata", {}),
                        "score": doc.get("score", 0)
                    }
                    for doc in relevant_docs
                ],
                "metrics": metrics,
                "processing_time": round(processing_time, 2)
            }
            
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
        """Classify query intent"""
        query_lower = query.lower()
        
        # Check for calculation intent
        if any(term in query_lower for term in [
            "calculate", "compute", "what is the", "total", "average",
            "dpi", "irr", "roi", "return", "performance"
        ]):
            return "calculation"
            
        # Check for definition intent    
        if any(term in query_lower for term in [
            "what does", "define", "explain", "mean", "definition",
            "describe", "how does", "why is"
        ]):
            return "definition"
            
        # Default to retrieval
        return "retrieval"
        
    def _build_prompt(
        self,
        query: str,
        context: List[Dict[str, Any]],
        metrics: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Build prompt with context"""
        # Start with system prompt
        prompt = self.system_prompt + "\n\n"
        
        # Add conversation history if any
        if conversation_history:
            prompt += "Previous conversation:\n"
            for msg in conversation_history[-3:]:  # Last 3 messages
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt += f"{role}: {content}\n"
            prompt += "\n"
        
        # Add context from vector search
        prompt += "Relevant context:\n"
        for doc in context:
            content = doc.get("content", "").strip()
            metadata = doc.get("metadata", {})
            prompt += f"Source ({metadata.get('source', 'unknown')}): {content}\n\n"
            
        # Add metrics if available
        if metrics:
            prompt += "Current fund metrics:\n"
            prompt += json.dumps(metrics, indent=2) + "\n\n"
            
        # Add user query
        prompt += f"User question: {query}\n"
        prompt += "Please provide a detailed answer using the above context. Cite sources where possible."
        
        return prompt
        
    async def _generate_response(self, prompt: str) -> str:
        """Generate response using LLM"""
        try:
            messages = [{"role": "user", "content": prompt}]
            response = await self.llm.apredict_messages(messages)
            return response.content
        except Exception as e:
            logger.exception("Error generating response")
            return "I apologize, but I'm having trouble generating a response. Please try again."