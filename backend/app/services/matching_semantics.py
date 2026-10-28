"""CPU MiniLM similarity using an already installed model. No inference API calls."""
import math
import threading
from functools import lru_cache

from app.config import settings

_lock = threading.Lock()


@lru_cache(maxsize=1)
def local_model():
    try:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
        class OfflineMiniLM(ONNXMiniLM_L6_V2):
            def _download_model_if_not_exists(self):
                folder = self.DOWNLOAD_PATH / self.EXTRACTED_FOLDER_NAME
                if not all((folder / name).is_file() for name in (
                    "config.json", "model.onnx", "special_tokens_map.json", "tokenizer_config.json", "tokenizer.json", "vocab.txt"
                )):
                    raise FileNotFoundError("Install the MiniLM model before enabling semantic matching")
        model = OfflineMiniLM(preferred_providers=["CPUExecutionProvider"])
        model._download_model_if_not_exists()
        return model
    except Exception:
        return None


@lru_cache(maxsize=512)
def vector(owner: str, text: str) -> tuple:
    # Owner is part of the bounded cache key; resume text is never persisted here.
    with _lock:
        model = local_model()
        if model is None:
            raise RuntimeError("Local semantic model unavailable")
        return tuple(float(v) for v in model([text])[0])


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
        return round(max(0, min(1, score)), 4), "all-MiniLM-L6-v2"
    except Exception:
        return None, "unavailable"
