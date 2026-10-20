"""LLM client initialisation.

Provides wrappers around LLM providers (Groq, OpenAI, Anthropic)
for structured generation, resume tailoring, cover letter writing,
and job description parsing.
"""
import re
import time

import httpx
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from app.config import settings
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic


DEFAULT_MODELS = {
    # llama-3.3-70b-versatile was retired from Groq; gpt-oss-120b handles tools + structured output.
    "groq": settings.GROQ_MODEL or "openai/gpt-oss-120b",
    "openai": settings.OPENAI_MODEL or "gpt-4o",
    "anthropic": settings.ANTHROPIC_MODEL or "claude-sonnet-5-5",
}

PROVIDER_PREFERENCE = ("anthropic", "openai", "groq")


def is_configured(provider: str) -> bool:
    """True when the provider's API key is set to something other than the .env.example placeholder."""
    key = {
        "groq": settings.GROQ_API_KEY,
        "openai": settings.OPENAI_API_KEY,
        "anthropic": settings.ANTHROPIC_API_KEY,
    }.get(provider, "")
    return bool(key) and not key.startswith("your-")


def get_llm_client(provider: str = "groq", model: str | None = None, temperature: float = 0.0, max_retries: int = 5):
    """Initialize and return the requested LLM client.

    Args:
        provider: The model provider ("groq", "anthropic", or "openai").
        model: Optional model override; defaults to DEFAULT_MODELS[provider].
        temperature: Sampling temperature.

    Returns:
        Chat client instance configured for LLM operations.
    """
    if provider == "groq":
        if not settings.GROQ_API_KEY or settings.GROQ_API_KEY == "your-groq-api-key":
            raise ValueError("GROQ_API_KEY is not set in environment or .env file.")
        name = model or DEFAULT_MODELS["groq"]
        return ChatGroq(
            model=name,
            api_key=settings.GROQ_API_KEY,
            temperature=temperature,
            # Free-tier limits are low (tokens per minute); back off and retry on 429s.
            max_retries=max_retries,
            # Qwen3 writes its reasoning into the reply unless it's hidden.
            **({"reasoning_format": "hidden"} if "qwen" in name.lower() else {}),
        )
    elif provider == "openai":
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your-openai-api-key":
            raise ValueError("OPENAI_API_KEY is not set in environment or .env file.")
        return ChatOpenAI(
            model=model or DEFAULT_MODELS["openai"],
            api_key=settings.OPENAI_API_KEY,
            temperature=temperature
        )
    elif provider == "anthropic":
        if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY == "your-anthropic-api-key":
            raise ValueError("ANTHROPIC_API_KEY is not set in environment or .env file.")
        return ChatAnthropic(
            model=model or DEFAULT_MODELS["anthropic"],
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=temperature,
            max_tokens=4096,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def default_provider() -> str:
    """The provider every agent uses: LLM_PROVIDER, or the first configured in PROVIDER_PREFERENCE."""
    if settings.LLM_PROVIDER and settings.LLM_PROVIDER != "auto":
        return settings.LLM_PROVIDER
    return next((p for p in PROVIDER_PREFERENCE if is_configured(p)), "groq")


# --- Model fallback --------------------------------------------------------------------

class ModelsExhausted(RuntimeError):
    """Every model in the chain is rate-limited or unavailable; the message is safe to show."""


# Model name -> monotonic time until which it's known to be rate-limited.
_cooldown: dict[str, float] = {}
_RETRY_IN = re.compile(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", re.IGNORECASE)


def _is_unavailable(error: Exception) -> bool:
    """Rate limits, quota and capacity errors: worth trying a different model."""
    text = f"{type(error).__name__} {error}".lower()
    return any(s in text for s in (
        "ratelimit", "rate limit", "rate_limit", "429", "quota", "over capacity", "503",
        "model_decommissioned", "model_not_found", "does not exist",
    ))


def _retry_after(error: Exception) -> float:
    """Seconds until the provider says to try again (default: one minute)."""
    m = _RETRY_IN.search(str(error))
    if not m or not any(m.groups()):
        return 60.0
    hours, minutes, seconds = (float(g) if g else 0.0 for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def _friendly_wait(seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    return f"about {minutes} minute{'s' if minutes != 1 else ''}" if minutes < 90 else f"about {round(minutes / 60)} hours"


class ModelChain:
    """Chat models tried in order; a rate-limited or busy model is skipped until it recovers.

    Looks like a LangChain chat model to callers: ``ainvoke``, ``astream``,
    ``bind_tools`` and ``with_structured_output`` all fall back the same way.
    """

    def __init__(self, models: list, names: list[str]):
        self.models, self.names = models, names

    def _derive(self, fn) -> "ModelChain":
        return ModelChain([fn(m) for m in self.models], self.names)

    def bind_tools(self, tools, **kwargs) -> "ModelChain":
        return self._derive(lambda m: m.bind_tools(tools, **kwargs))

    def with_structured_output(self, schema, **kwargs) -> "ModelChain":
        return self._derive(lambda m: m.with_structured_output(schema, **kwargs))

    def _order(self) -> list[int]:
        now = time.monotonic()
        ready = [i for i, n in enumerate(self.names) if _cooldown.get(n, 0) <= now]
        return ready or [min(range(len(self.names)), key=lambda i: _cooldown.get(self.names[i], 0))]

    def _note(self, index: int, error: Exception):
        _cooldown[self.names[index]] = time.monotonic() + _retry_after(error)
        print(f"Model {self.names[index]} unavailable, trying the next one: {str(error)[:160]}")

    def _exhausted(self, last: Exception) -> ModelsExhausted:
        wait = min((_cooldown.get(n, 0) - time.monotonic() for n in self.names), default=60)
        return ModelsExhausted(
            f"All the AI models available to you are at their usage limit right now. The first is free again in "
            f"{_friendly_wait(max(wait, 60))}. (Groq's free tier allows a daily token budget per model.) Last error: {str(last)[:200]}"
        )

    async def ainvoke(self, input, config=None, **kwargs):
        last: Exception | None = None
        for i in self._order():
            try:
                return await self.models[i].ainvoke(input, config, **kwargs)
            except Exception as e:
                if not _is_unavailable(e):
                    raise
                self._note(i, e)
                last = e
        raise self._exhausted(last)

    def invoke(self, input, config=None, **kwargs):
        last: Exception | None = None
        for i in self._order():
            try:
                return self.models[i].invoke(input, config, **kwargs)
            except Exception as e:
                if not _is_unavailable(e):
                    raise
                self._note(i, e)
                last = e
        raise self._exhausted(last)

    async def astream(self, input, config=None, **kwargs):
        last: Exception | None = None
        for i in self._order():
            started = False
            try:
                async for chunk in self.models[i].astream(input, config, **kwargs):
                    started = True
                    yield chunk
                return
            except Exception as e:
                # Once output has reached the user, switching models would garble it.
                if started or not _is_unavailable(e):
                    raise
                self._note(i, e)
                last = e
        raise self._exhausted(last)


def groq_models(task: str = "quality") -> list[str]:
    """Groq models in the order to try. ``light`` tasks start with the smaller model."""
    primary = settings.GROQ_MODEL or "openai/gpt-oss-120b"
    fallbacks = [m.strip() for m in settings.GROQ_FALLBACK_MODELS.split(",") if m.strip()]
    order = [primary, *fallbacks]
    if task == "light" and settings.GROQ_LIGHT_MODEL:
        order = [settings.GROQ_LIGHT_MODEL, *order]
    return list(dict.fromkeys(order))


def get_chat_llm(provider: str, *, model: str | None = None, temperature: float = 0.0, task: str = "quality"):
    """A chat model for ``provider``; on Groq, a chain across models with separate quotas."""
    if provider != "groq":
        return get_llm_client(provider, model=model, temperature=temperature)
    names = [model] if model else groq_models(task)
    # Few retries per model: moving to another model's quota beats waiting on this one.
    return ModelChain([get_llm_client("groq", model=n, temperature=temperature, max_retries=1) for n in names], names)


def get_default_llm(temperature: float = 0.0, task: str = "quality"):
    """Chat model for agents, from the single provider setting.

    ``task="light"`` (parsing, short messages) prefers the smaller, cheaper model.
    """
    return get_chat_llm(default_provider(), temperature=temperature, task=task)


def with_structured(llm, schema):
    """Structured output that works the same across providers.

    OpenAI's default mode is strict JSON schema, which rejects models with
    optional/defaulted fields like ours; tool calling works everywhere.
    """
    if isinstance(llm, ModelChain):
        return llm._derive(lambda m: with_structured(m, schema))
    if isinstance(llm, ChatOpenAI):
        return llm.with_structured_output(schema, method="function_calling")
    return llm.with_structured_output(schema)

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
        self.api_url = f"https://router.huggingface.co/hf-inference/models/{model_id}/pipeline/feature-extraction"
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
        # After the first failure, use the backup for the rest of the process instead of
        # paying for a failing network call (and logging it) on every embed.
        self.primary_failed = False

    def _fail_over(self, error: Exception):
        self.primary_failed = True
        print(f"⚠️ Warning: Primary embedding API failed ({error}). Using the offline model from now on.")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self.primary_failed:
            try:
                return self.primary.embed_documents(texts)
            except Exception as e:
                self._fail_over(e)
        return self.backup.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if not self.primary_failed:
            try:
                return self.primary.embed_query(text)
            except Exception as e:
                self._fail_over(e)
        return self.backup.embed_query(text)


# Embedding model identity -> vector collection. Vectors from different models (or dimensions)
# must never share a collection. MiniLM keeps the original collection name so existing data stays.
EMBEDDING_COLLECTIONS = {
    "minilm": "resume_sections",
    "openai-text-embedding-3-small": "resume_sections_openai-3-small",
}


def get_embeddings() -> tuple[str, Embeddings]:
    """Return (model id, client) for resume embeddings, per EMBEDDINGS_PROVIDER."""
    provider = (settings.EMBEDDINGS_PROVIDER or "local").lower()
    if provider == "openai" and is_configured("openai"):
        return "openai-text-embedding-3-small", OpenAIEmbeddings(model="text-embedding-3-small", api_key=settings.OPENAI_API_KEY)
    hf_token = settings.HUGGINGFACE_API_KEY
    if provider == "huggingface" and hf_token and not hf_token.startswith("your-"):
        # Same MiniLM model as the local one, so a fallback never mixes vector spaces.
        return "minilm", FallbackEmbeddings(primary=HuggingFaceAPIEmbeddings(api_key=hf_token), backup=ChromaDefaultEmbeddings())
    return "minilm", ChromaDefaultEmbeddings()


def get_embeddings_client():
    """Embeddings client only (see get_embeddings for the model id)."""
    return get_embeddings()[1]
