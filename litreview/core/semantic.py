"""Optional semantic retrieval (spec §10, core/semantic.py) — opt-in only.

Explicit safety policy: models are never downloaded automatically. Unless
``ENABLE_SEMANTIC_DOWNLOAD`` is set, offline mode is forced via HF env vars,
and any load failure disables the feature silently.
"""

from __future__ import annotations

import os

_model = None
_failed = False


def available() -> bool:
    from ..config import get_settings
    settings = get_settings()
    return settings.semantic_retrieval and not _failed


def _load():
    global _model, _failed
    if _model is not None or _failed:
        return _model
    from ..config import get_settings
    settings = get_settings()
    if not settings.semantic_download:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(settings.semantic_model)
    except Exception:  # noqa: BLE001 — load failure disables silently (spec)
        _failed = True
        _model = None
    return _model


def rank(query: str, texts: list[str]) -> list[int]:
    """Indexes of ``texts`` sorted by cosine similarity to ``query``.
    Empty list when the feature is unavailable."""
    if not available():
        return []
    model = _load()
    if model is None:
        return []
    import numpy as np
    embeddings = model.encode([query] + texts, normalize_embeddings=True)
    scores = embeddings[1:] @ embeddings[0]
    return list(np.argsort(-scores))
