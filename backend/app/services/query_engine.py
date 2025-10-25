"""
Query engine service for RAG-based question answering
"""
from typing import Dict, Any, List, Optional
import time
from langchain_openai import ChatOpenAI
from langchain_community.llms import Ollama
from langchain.prompts import ChatPromptTemplate
from llama_cpp import Llama
from app.core.config import settings
from app.services.vector_store import VectorStore
from app.services.metrics_calculator import MetricsCalculator
from sqlalchemy.orm import Session


class QueryEngine:
    """RAG-based query engine for fund analysis"""
    
    def __init__(self, db: Session):
        self.db = db
        self.vector_store = VectorStore()
        self.metrics_calculator = MetricsCalculator(db)
        self.llm = self._initialize_llm()
    
    def _initialize_llm(self):
        """Initialize LLM"""
        return Llama(
            model_path=settings.RAG_MODEL,
            verbose=False,
            n_ctx=2048,
        )
    
    async def process_query(
        self, 
        query: str, 
        fund_id: Optional[int] = None,
        conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Process a user query using RAG
        
        Args:
            query: User question
            fund_id: Optional fund ID for context
            conversation_history: Previous conversation messages
            
        Returns:
            Response with answer, sources, and metrics
        """
        start_time = time.time()
        
        # Step 1: Classify query intent
        intent = await self._classify_intent(query)
        
        # Step 2: Retrieve relevant context from vector store
        filter_metadata = {"fund_id": fund_id} if fund_id else None
        relevant_docs = await self.vector_store.similarity_search(
            query=query,
            k=settings.TOP_K_RESULTS,
            filter_metadata=filter_metadata
        )
        
        # Step 3: Calculate metrics if needed
        metrics = None
        if intent == "calculation" and fund_id:
            metrics = self.metrics_calculator.calculate_all_metrics(fund_id)
        
        # Step 4: Generate response using LLM
        answer = await self._generate_response(
            query=query,
            context=relevant_docs,
            metrics=metrics,
            conversation_history=conversation_history or []
        )
        
        processing_time = time.time() - start_time
        
        return {
            "answer": answer,
            "sources": [
                {
                    "content": doc["content"],
                    "metadata": {
                        k: v for k, v in doc.items() 
                        if k not in ["content", "score"]
                    },
                    "score": doc.get("score")
                }
                for doc in relevant_docs
            ],
            "metrics": metrics,
            "processing_time": round(processing_time, 2)
        }
    
    async def _classify_intent(self, query: str) -> str:
        """
        Classify query intent
        
        Returns:
            'calculation', 'definition', 'retrieval', or 'general'
        """
        query_lower = query.lower()
        
        # Calculation keywords
        calc_keywords = [
            "calculate", "what is the", "current", "dpi", "irr", "tvpi", 
            "rvpi", "pic", "paid-in capital", "return", "performance"
        ]
        if any(keyword in query_lower for keyword in calc_keywords):
            return "calculation"
        
        # Definition keywords
        def_keywords = [
            "what does", "mean", "define", "explain", "definition", 
            "what is a", "what are"
        ]
        if any(keyword in query_lower for keyword in def_keywords):
            return "definition"
        
        # Retrieval keywords
        ret_keywords = [
            "show me", "list", "all", "find", "search", "when", 
            "how many", "which"
        ]
        if any(keyword in query_lower for keyword in ret_keywords):
            return "retrieval"
        
        return "general"
    
    async def _generate_response(
        self,
        query: str,
        context: List[Dict[str, Any]],
        metrics: Optional[Dict[str, Any]],
        conversation_history: List[Dict[str, str]]
    ) -> str:
        """Generate response using LLM (llama_cpp)"""
        
        # Build context string
        context_str = "\n\n".join([
            f"[Source {i+1}]\n{doc['content']}"
            for i, doc in enumerate(context[:3])  # Use top 3 sources
        ])
        
        # Build metrics string
        metrics_str = ""
        if metrics:
            metrics_str = "\n\nAvailable Metrics:\n"
            for key, value in metrics.items():
                if value is not None:
                    metrics_str += f"- {key.upper()}: {value}\n"
        
        # Build conversation history string
        history_str = ""
        if conversation_history:
            history_str = "\n\nPrevious Conversation:\n"
            for msg in conversation_history[-3:]:  # Last 3 messages
                history_str += f"{msg['role']}: {msg['content']}\n"
        
        system_content = (
            "You are a financial analyst assistant specializing in private equity fund performance.\n\n"
            "Your role:\n"
            "- Answer questions about fund performance using provided context\n"
            "- Calculate metrics like DPI, IRR when asked\n"
            "- Explain complex financial terms in simple language\n"
            "- Always cite your sources from the provided documents\n\n"
            "When calculating:\n"
            "- Use the provided metrics data\n"
            "- Show your work step-by-step\n"
            "- Explain any assumptions made\n\n"
            "Format your responses:\n"
            "- Be concise but thorough\n"
            "- Use bullet points for lists\n"
            "- Bold important numbers using **number**\n"
            "- Provide context for metrics"
        )

        user_content = (
            f"Context from documents:\n{context_str}"
            f"{metrics_str}"
            f"{history_str}\n\n"
            f"Question: {query}\n\n"
            "Please provide a helpful answer based on the context and metrics provided. "
            "Cite source numbers like [Source 1], [Source 2] where relevant."
        )
        
        # Generate response
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        print(messages)
        
        try:
            response = self.llm.create_chat_completion(
                messages=messages,
                max_tokens=768,
            )
            print(response)
            if hasattr(response, 'content'):
                return response.content
            return str(response)
        except Exception as e:
            return f"I apologize, but I encountered an error generating a response: {str(e)}"
