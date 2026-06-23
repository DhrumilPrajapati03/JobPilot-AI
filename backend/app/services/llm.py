"""LLM client initialisation.

Provides wrappers around LLM providers (Groq, OpenAI, Anthropic)
for structured generation, resume tailoring, cover letter writing,
and job description parsing.
"""

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
            model="llama-3.1-70b-versatile",
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

