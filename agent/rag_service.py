import os
from typing import List, Dict

from langchain_community.document_loaders import TextLoader, CSVLoader
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
import yaml
import os

PROMPTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt.yaml")
with open(PROMPTS_FILE, "r") as f:
    PROMPTS = yaml.safe_load(f)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# Ensure access to paths
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import POLICY_FILE, FAQ_FILE, INTERNATIONAL_POLICY_FILE, PER_DIEM_FILE, LLM_MODEL, GOOGLE_API_KEY


class PolicyQA_RAG:
    """Retrieval-Augmented Generation (RAG) assistant for Travel Policy."""

    def __init__(self):
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", 
            google_api_key=GOOGLE_API_KEY
        )
        self.llm = ChatGoogleGenerativeAI(
            model=LLM_MODEL, 
            google_api_key=GOOGLE_API_KEY, 
            temperature=0.2
        )
        self.vectorstore = None
        self._initialize_knowledge_base()

    def _initialize_knowledge_base(self):
        """Loads and indexes the policy files into an in-memory FAISS store."""
        docs = []
        for file_path in [POLICY_FILE, FAQ_FILE, INTERNATIONAL_POLICY_FILE]:
            if os.path.exists(file_path):
                # Simple text loader
                loader = TextLoader(file_path, encoding='utf-8')
                loaded_docs = loader.load()
                docs.extend(loaded_docs)
                
        # Load CSV tables
        if os.path.exists(PER_DIEM_FILE):
            csv_loader = CSVLoader(PER_DIEM_FILE, encoding='utf-8')
            docs.extend(csv_loader.load())
        
        # Build FAISS generic vector store (in-memory)
        if docs:
            # We split the docs slightly for better retrieval precision
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
            splits = text_splitter.split_documents(docs)
            self.vectorstore = FAISS.from_documents(splits, self.embeddings)

    def answer_query(self, query: str, history: List[Dict[str, str]] = None) -> str:
        """Searches policy and generates a conversational answer."""
        if not self.vectorstore:
            return "Knowledge base not initialized. Policy files missing."

        # Search top 3 relevant chunks
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 3})
        relevant_docs = retriever.invoke(query)
        context = "\n\n".join([doc.page_content for doc in relevant_docs])

        prefix = PROMPTS.get("rag_chatbot_system_prefix", {}).get("v1", "You are a helpful assistant.\n")
        
        system_prompt = (
            f"{prefix}\n"
            f"{context}\n"
            "----------------------\n"
        )

        messages = [SystemMessage(content=system_prompt)]
        
        # Inject Chat History
        if history:
            # Take last 6 messages to prevent context overflow
            for msg in history[-6:]:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        # Append exact final query
        messages.append(HumanMessage(content=query))

        response = self.llm.invoke(messages)
        return response.content

# Singleton instance
rag_service = PolicyQA_RAG()
