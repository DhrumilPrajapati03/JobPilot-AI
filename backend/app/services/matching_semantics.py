"""Semantic similarity from local embeddings (Ollama, OLLAMA_EMBED_MODEL). No cloud calls.

Replaces the ONNX MiniLM model that came with Chroma (plan Day 1: Chroma and
onnxruntime removed). When Ollama is not reachable, similarity() returns
(None, "unavailable") and matching falls back to its lexical score; the probe is
retried after RETRY_SECONDS instead of being cached forever.
"""
import math
import threading
import time
from functools import lru_cache

from app.config import settings

RETRY_SECONDS = 60.0
_lock = threading.Lock()
_state = {"model": None, "checked": 0.0}


def model_name() -> str:
    return settings.OLLAMA_EMBED_MODEL


def local_model():
    """The embeddings client when Ollama answers, else None (re-probed at most once a minute)."""
    with _lock:
        if _state["model"] is not None:
            return _state["model"]
        if time.monotonic() - _state["checked"] < RETRY_SECONDS and _state["checked"]:
            return None
        _state["checked"] = time.monotonic()
        try:
            from app.services.llm import OllamaEmbeddings
            model = OllamaEmbeddings()
            model.embed_query("ping")
            _state["model"] = model
        except Exception:
            _state["model"] = None
        return _state["model"]


def reset() -> None:
    with _lock:
        _state.update(model=None, checked=0.0)
    vector.cache_clear()


@lru_cache(maxsize=512)
def vector(owner: str, text: str) -> tuple:
    # Owner is part of the bounded cache key; resume text is never persisted here.
    model = local_model()
    if model is None:
        raise RuntimeError("Local semantic model unavailable")
    return tuple(float(v) for v in model.embed_query(text))


def similarity(left: str, right: str, owner: str = "") -> tuple[float | None, str]:
    if not settings.MATCHING_SEMANTIC:
        return None, "disabled"
    if not left.strip() or not right.strip():
        return None, "insufficient_text"
    try:
        a, b = vector(owner, left[:4000]), vector(owner, right[:4000])
        norm = math.sqrt(sum(v*v for v in a) * sum(v*v for v in b))
        score = sum(x*y for x, y in zip(a, b)) / norm if norm else 0.0
        if not math.isfinite(score): raise ValueError("Invalid embedding")
        return round(max(0, min(1, score)), 4), model_name()
    except Exception:
        return None, "unavailable"
