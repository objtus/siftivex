"""EmbeddingGemma 2 via sentence-transformers (pilot)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


class Gemma2Embedder:
    def __init__(
        self,
        model_id: str = "google/embeddinggemma-2",
        dtype: str = "bfloat16",
        *,
        device: str | None = None,
    ):
        import torch
        from sentence_transformers import SentenceTransformer

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float32
        if device == "cuda" and dtype == "bfloat16" and torch.cuda.is_bf16_supported():
            torch_dtype = torch.bfloat16
        try:
            self._model = SentenceTransformer(
                model_id,
                model_kwargs={"torch_dtype": torch_dtype},
                config_kwargs={"audio_config": None},
                device=device,
            )
        except Exception:
            self._model = SentenceTransformer(
                model_id,
                model_kwargs={"torch_dtype": torch.float32},
                config_kwargs={"audio_config": None},
                device="cpu",
            )
            device = "cpu"
            torch_dtype = torch.float32
        self.model_id = model_id
        self.device = device
        self.dtype = "bfloat16" if torch_dtype == torch.bfloat16 else "float32"

    def embed_image_path(self, path: Path) -> list[float]:
        vec = self._model.encode(
            {"image": str(path)},
            normalize_embeddings=True,
        )
        return np.asarray(vec, dtype=np.float32).tolist()

    def embed_query(self, text: str) -> list[float]:
        vec = self._model.encode(text, prompt_name="SearchQuery", normalize_embeddings=True)
        return np.asarray(vec, dtype=np.float32).tolist()

    def similarity(self, a: list[float], b: list[float]) -> float:
        va = np.asarray(a, dtype=np.float32)
        vb = np.asarray(b, dtype=np.float32)
        return float(np.dot(va, vb))
