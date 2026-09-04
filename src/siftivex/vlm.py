"""VLM client for llama.cpp OpenAI-compatible vision API."""

from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml
from PIL import Image

from siftivex.paths import CONFIG_DIR
from siftivex.tag_vocabulary import (
    build_system_prompt,
    build_user_prompt,
    load_tag_vocabulary,
    validate_namespace_tags,
)

VLM_CONFIG = CONFIG_DIR / "vlm.yaml"


@dataclass
class VlmTagResult:
    namespace_tags: dict[str, str]
    flat_tags: list[str]
    caption: str
    raw: dict[str, Any]


def load_vlm_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or VLM_CONFIG
    if not config_path.exists():
        example = CONFIG_DIR / "vlm.yaml.example"
        raise FileNotFoundError(f"VLM config not found: {config_path} (copy from {example})")
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _image_to_data_url(path: Path, max_size: int, quality: int) -> str:
    with Image.open(path) as img:
        if getattr(img, "is_animated", False):
            img.seek(0)
        img = img.convert("RGB")
        img.thumbnail((max_size, max_size))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


class VlmClient:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        vocabulary: dict[str, Any] | None = None,
    ) -> None:
        self.config = config or load_vlm_config()
        self.vocabulary = vocabulary if vocabulary is not None else load_tag_vocabulary()
        self.base_url = self.config["base_url"].rstrip("/")
        self.model = self.config["model"]

    def tag_image(self, path: Path, priority_tags: list[str] | None = None) -> VlmTagResult:
        system_prompt = build_system_prompt(self.vocabulary)
        user_text = build_user_prompt(priority_tags or [])

        data_url = _image_to_data_url(
            path,
            max_size=int(self.config.get("max_image_size", 768)),
            quality=int(self.config.get("jpeg_quality", 85)),
        )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "max_tokens": int(self.config.get("max_tokens", 512)),
            "temperature": float(self.config.get("temperature", 0.1)),
        }
        if not self.config.get("enable_thinking", False):
            payload["chat_template_kwargs"] = {"enable_thinking": False}

        timeout = float(self.config.get("timeout_seconds", 180))
        last_error: Exception | None = None
        tokens = int(self.config.get("max_tokens", 512))
        for attempt in range(2):
            payload["max_tokens"] = tokens * (2 if attempt else 1)
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(f"{self.base_url}/chat/completions", json=payload)
                    resp.raise_for_status()
                    body = resp.json()
                message = body["choices"][0]["message"]
                content = (message.get("content") or "").strip()
                if not content and message.get("reasoning_content"):
                    raise ValueError(
                        "VLM returned reasoning only; increase max_tokens or disable thinking"
                    )
                raw = _extract_json(content)
                break
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                continue
        else:
            raise last_error or RuntimeError("VLM tagging failed")

        namespace = validate_namespace_tags(raw.get("namespace_tags", {}))
        flat = raw.get("flat_tags", [])
        if not isinstance(flat, list):
            flat = []
        flat_tags = [str(t).strip() for t in flat if str(t).strip()]
        caption = str(raw.get("caption", "")).strip()

        return VlmTagResult(
            namespace_tags=namespace,
            flat_tags=flat_tags,
            caption=caption,
            raw=raw,
        )
