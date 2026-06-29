"""LLM client initialisation.

Provides wrappers around LLM providers (Groq, OpenAI, Anthropic)
for structured generation, resume tailoring, cover letter writing,
and job description parsing.
"""
import httpx
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from app.config import settings
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic


def get_llm_client(provider: str = "groq"):
    """Initialize and return the requested LLM client.

    Args:
        provider: The model provider ("groq", "anthropic", or "openai").

    Returns:
        Chat client instance configured for LLM operations.
    """
    if provider == "groq":
        if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "your-groq-api-key":
            raise ValueError("GROQ_API_KEY is not set in environment or .env file.")
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=settings.GROQ_API_KEY,
            temperature=0.0
        )
    elif provider == "openai":
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your-openai-api-key":
            raise ValueError("OPENAI_API_KEY is not set in environment or .env file.")
        return ChatOpenAI(
            model="gpt-4o",
            api_key=settings.OPENAI_API_KEY,
            temperature=0.0
        )
    elif provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "your-anthropic-api-key":
            raise ValueError("ANTHROPIC_API_KEY is not set in environment or .env file.")
        return ChatAnthropic(
            model="claude-3-5-sonnet-20240620",
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0.0
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")

import chromadb.utils.embedding_functions as ef

class ChromaDefaultEmbeddings(Embeddings):
    """Local, offline embedding generator using Chroma's default sentence-transformers model.
    
    Runs completely offline on your CPU using onnxruntime.
    """
    def __init__(self):
        # ONNXMiniLM_L6_V2 loads the model locally
        self.ef = ef.ONNXMiniLM_L6_V2()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.ef(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.ef([text])[0]


class HuggingFaceAPIEmbeddings(Embeddings):
    """Generates embeddings by calling Hugging Face's Serverless Inference API."""
    def __init__(self, api_key: str, model_id: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.api_url = f"https://api-inference.huggingface.co/models/{model_id}"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        with httpx.Client() as client:
            response = client.post(
                self.api_url,
                headers=self.headers,
                json={"inputs": texts, "options": {"wait_for_model": True}},
                timeout=30.0
            )
            if response.status_code != 200:
                raise ValueError(
                    f"Hugging Face API returned status {response.status_code}: {response.text}"
                )
            return response.json()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._call_api(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._call_api([text])[0]


class FallbackEmbeddings(Embeddings):
    """A wrapper that delegates to a primary embedding API, but falls back to a 
    backup local model if the primary API fails (due to network, downtime, etc.).
    """
    def __init__(self, primary: Embeddings, backup: Embeddings):
        self.primary = primary
        self.backup = backup

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            return self.primary.embed_documents(texts)
        except Exception as e:
            print(f"⚠️ Warning: Primary embedding API failed ({str(e)}). Falling back to offline model.")
            return self.backup.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        try:
            return self.primary.embed_query(text)
        except Exception as e:
            print(f"⚠️ Warning: Primary embedding API failed ({str(e)}). Falling back to offline model.")
            return self.backup.embed_query(text)


def get_embeddings_client():
    """Initializes and returns the embeddings client (OpenAI, Hugging Face API, or Local CPU)."""
    # 1. Check if OpenAI is configured
    has_openai = settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "your-openai-api-key"
    if has_openai:
        return OpenAIEmbeddings(
            model="text-embedding-3-small", 
            api_key=settings.OPENAI_API_KEY
        )
    
    # 2. Check if Hugging Face is configured
    hf_token = getattr(settings, "HUGGINGFACE_API_KEY", None)
    if hf_token and hf_token != "your-huggingface-api-key":
        # Return the Fallback wrapper: HF API as primary, Offline local as backup!
        return FallbackEmbeddings(
            primary=HuggingFaceAPIEmbeddings(api_key=hf_token),
            backup=ChromaDefaultEmbeddings()
        )
        
    # 3. Default to local offline CPU model if no keys are provided
    return ChromaDefaultEmbeddings()
