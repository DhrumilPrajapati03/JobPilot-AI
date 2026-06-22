"""LLM client initialisation.

Provides wrappers around Anthropic Claude and OpenAI GPT models
for structured generation, resume tailoring, cover letter writing,
and job description parsing.
"""

from app.config import settings


def get_llm_client(provider: str = "anthropic"):
    """Initialize and return the requested LLM client.

    Args:
        provider: The model provider ("anthropic" or "openai").

    Returns:
        Chat client instance configured for LLM operations.
    """
    if provider == "anthropic":
        # from langchain_anthropic import ChatAnthropic
        # return ChatAnthropic(model="claude-3-5-sonnet-20240620", api_key=settings.ANTHROPIC_API_KEY)
        raise NotImplementedError("Anthropic LLM client not yet configured.")
    elif provider == "openai":
        # from langchain_openai import ChatOpenAI
        # return ChatOpenAI(model="gpt-4o", api_key=settings.OPENAI_API_KEY)
        raise NotImplementedError("OpenAI LLM client not yet configured.")
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
