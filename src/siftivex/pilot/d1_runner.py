"""LiquidAI d1-3B decision runner for pilot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image


class D1Runner:
    def __init__(
        self,
        model_id: str = "LiquidAI/d1-3B",
        *,
        prefer_cuda: bool = False,
        device: str | None = None,
    ):
        import torch
        from transformers import AutoModel

        self.model_id = model_id
        target = device
        if not target and prefer_cuda and torch.cuda.is_available():
            target = "cuda"
        if not target:
            target = "cpu"

        self._device = target
        dtype = torch.float32
        model = AutoModel.from_pretrained(model_id, trust_remote_code=True, dtype=dtype)
        if target != "cpu" and torch.cuda.is_available():
            try:
                torch.cuda.empty_cache()
                dev = torch.device(target)
                model = model.to(dev, dtype=torch.bfloat16)
                dtype = torch.bfloat16
            except Exception:
                model = model.to("cpu", dtype=torch.float32)
                self._device = "cpu"
        else:
            model = model.to("cpu", dtype=torch.float32)
            self._device = "cpu"
        self._model = model
        self._model.eval()
        self._dtype = dtype

    def decide(
        self,
        image_path: Path,
        questions: dict[str, dict[str, Any]],
        *,
        state_text: str | None = None,
    ) -> dict[str, Any]:
        from transformers.image_utils import load_image

        image = load_image(str(image_path))
        state = state_text if state_text else None
        out = self._model.system_one(state, questions, images=[image])
        return out
