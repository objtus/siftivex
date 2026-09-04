"""CLIP embedding and LanceDB storage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import lancedb
import numpy as np
import open_clip
import pyarrow as pa
import torch
from PIL import Image

from siftivex.paths import DEFAULT_LANCE_PATH

DEFAULT_MODEL = "ViT-B-32"
DEFAULT_PRETRAINED = "openai"
TABLE_NAME = "embeddings"


def _default_device() -> str:
    """Prefer secondary GPU for CLIP (primary often runs VLM/llama-swap)."""
    import os

    if env := os.environ.get("SIFTIVEX_DEVICE"):
        return env
    if not torch.cuda.is_available():
        return "cpu"
    if torch.cuda.device_count() > 1:
        return "cuda:1"
    return "cuda"


@dataclass
class EmbedResult:
    image_id: str
    vector: list[float]
    model: str


class Embedder:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        pretrained: str = DEFAULT_PRETRAINED,
        device: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.pretrained = pretrained
        if device is None:
            device = _default_device()
        self.device = device
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        self.model = self.model.to(self.device).eval()
        self.tokenizer = open_clip.get_tokenizer(model_name)
        self.model_label = f"{model_name}:{pretrained}"

    def _load_image(self, path: Path) -> Image.Image:
        with Image.open(path) as img:
            if getattr(img, "is_animated", False):
                img.seek(0)
            return img.convert("RGB")

    @torch.inference_mode()
    def embed_image(self, path: Path) -> list[float]:
        image = self.preprocess(self._load_image(path)).unsqueeze(0).to(self.device)
        features = self.model.encode_image(image)
        features = features / features.norm(dim=-1, keepdim=True)
        return features.squeeze(0).cpu().tolist()

    @torch.inference_mode()
    def embed_text(self, text: str) -> list[float]:
        tokens = self.tokenizer([text]).to(self.device)
        features = self.model.encode_text(tokens)
        features = features / features.norm(dim=-1, keepdim=True)
        return features.squeeze(0).cpu().tolist()


class EmbeddingStore:
    def __init__(self, lance_path: Path | None = None) -> None:
        self.path = lance_path or DEFAULT_LANCE_PATH
        self.path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.path))

    def _schema(self) -> pa.Schema:
        return pa.schema(
            [
                pa.field("image_id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), 512)),
                pa.field("model", pa.string()),
            ]
        )

    def open_table(self, vector_dim: int = 512):
        if TABLE_NAME in self.db.table_names():
            return self.db.open_table(TABLE_NAME)
        return self.db.create_table(
            TABLE_NAME,
            schema=pa.schema(
                [
                    pa.field("image_id", pa.string()),
                    pa.field("vector", pa.list_(pa.float32(), vector_dim)),
                    pa.field("model", pa.string()),
                ]
            ),
        )

    def upsert(self, results: list[EmbedResult]) -> int:
        if not results:
            return 0
        dim = len(results[0].vector)
        table = self.open_table(dim)
        ids = [r.image_id for r in results]
        if ids and TABLE_NAME in self.db.table_names():
            id_list = ", ".join(f"'{i}'" for i in ids)
            table.delete(f"image_id IN ({id_list})")
        rows = [{"image_id": r.image_id, "vector": r.vector, "model": r.model} for r in results]
        table.add(rows)
        return len(rows)

    def search(self, query_vector: list[float], limit: int = 10) -> list[tuple[str, float]]:
        table = self.open_table(len(query_vector))
        hits = (
            table.search(query_vector)
            .metric("cosine")
            .limit(limit)
            .to_list()
        )
        return [(h["image_id"], float(h["_distance"])) for h in hits]
