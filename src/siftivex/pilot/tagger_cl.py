"""cl_tagger v1.02 ONNX (cella110n/cl_tagger) for pilot runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

DEFAULT_REPO = "cella110n/cl_tagger"
DEFAULT_ONNX = "cl_tagger_1_02/model.onnx"
DEFAULT_MAPPING = "cl_tagger_1_02/tag_mapping.json"


@dataclass
class LabelData:
    names: list[str | None]
    rating: np.ndarray
    general: np.ndarray
    artist: np.ndarray
    character: np.ndarray
    copyright: np.ndarray
    meta: np.ndarray
    quality: np.ndarray
    model: np.ndarray


def _stable_sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(x, -30, 30)))


def pil_ensure_rgb(image: Image.Image) -> Image.Image:
    if image.mode not in ["RGB", "RGBA"]:
        image = image.convert("RGBA") if "transparency" in image.info else image.convert("RGB")
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        image = background
    return image


def pil_pad_square(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width == height:
        return image
    new_size = max(width, height)
    new_image = Image.new(image.mode, (new_size, new_size), (255, 255, 255))
    paste_position = ((new_size - width) // 2, (new_size - height) // 2)
    new_image.paste(image, paste_position)
    return new_image


def preprocess_image(image: Image.Image, target_size: tuple[int, int] = (448, 448)) -> np.ndarray:
    image = pil_ensure_rgb(image)
    image = pil_pad_square(image)
    image_resized = image.resize(target_size, Image.BICUBIC)
    img_array = np.array(image_resized, dtype=np.float32) / 255.0
    img_array = img_array.transpose(2, 0, 1)
    img_array = img_array[::-1, :, :]  # RGB -> BGR
    mean = np.array([0.5, 0.5, 0.5], dtype=np.float32).reshape(3, 1, 1)
    std = np.array([0.5, 0.5, 0.5], dtype=np.float32).reshape(3, 1, 1)
    img_array = (img_array - mean) / std
    return np.expand_dims(img_array, axis=0).astype(np.float32)


def load_tag_mapping(mapping_path: Path) -> LabelData:
    tag_mapping_data = json.loads(mapping_path.read_text(encoding="utf-8"))
    if isinstance(tag_mapping_data, dict) and "idx_to_tag" in tag_mapping_data:
        idx_to_tag = {int(k): v for k, v in tag_mapping_data["idx_to_tag"].items()}
        tag_to_category = tag_mapping_data["tag_to_category"]
    elif isinstance(tag_mapping_data, dict):
        tag_mapping_data_int_keys = {int(k): v for k, v in tag_mapping_data.items()}
        idx_to_tag = {idx: data["tag"] for idx, data in tag_mapping_data_int_keys.items()}
        tag_to_category = {data["tag"]: data["category"] for data in tag_mapping_data_int_keys.values()}
    else:
        raise ValueError("Unsupported tag_mapping.json format")

    names: list[str | None] = [None] * (max(idx_to_tag.keys()) + 1)
    rating, general, artist, character, copyright_tags, meta, quality, model_name = [], [], [], [], [], [], [], []
    for idx, tag in idx_to_tag.items():
        if idx >= len(names):
            names.extend([None] * (idx - len(names) + 1))
        names[idx] = tag
        category = tag_to_category.get(tag, "Unknown")
        idx_int = int(idx)
        if category == "Rating":
            rating.append(idx_int)
        elif category == "General":
            general.append(idx_int)
        elif category == "Artist":
            artist.append(idx_int)
        elif category == "Character":
            character.append(idx_int)
        elif category == "Copyright":
            copyright_tags.append(idx_int)
        elif category == "Meta":
            meta.append(idx_int)
        elif category == "Quality":
            quality.append(idx_int)
        elif category == "Model":
            model_name.append(idx_int)

    return LabelData(
        names=names,
        rating=np.array(rating, dtype=np.int64),
        general=np.array(general, dtype=np.int64),
        artist=np.array(artist, dtype=np.int64),
        character=np.array(character, dtype=np.int64),
        copyright=np.array(copyright_tags, dtype=np.int64),
        meta=np.array(meta, dtype=np.int64),
        quality=np.array(quality, dtype=np.int64),
        model=np.array(model_name, dtype=np.int64),
    )


def get_tags(
    probs: np.ndarray,
    labels: LabelData,
    gen_threshold: float,
    char_threshold: float,
    max_tags: int,
) -> list[dict[str, Any]]:
    """Return flat list of {tag, score, category} sorted by score."""
    by_cat: dict[str, list[tuple[str, float]]] = {
        "rating": [],
        "general": [],
        "character": [],
        "copyright": [],
        "artist": [],
        "meta": [],
        "quality": [],
        "model": [],
    }

    if len(labels.rating) > 0:
        valid = labels.rating[labels.rating < len(probs)]
        if len(valid) > 0:
            rp = probs[valid]
            li = int(np.argmax(rp))
            gi = int(valid[li])
            name = labels.names[gi]
            if name:
                by_cat["rating"].append((name, float(rp[li])))

    category_map = {
        "general": (labels.general, gen_threshold),
        "character": (labels.character, char_threshold),
        "copyright": (labels.copyright, char_threshold),
        "artist": (labels.artist, char_threshold),
        "meta": (labels.meta, gen_threshold),
        "model": (labels.model, gen_threshold),
    }
    for category, (indices, threshold) in category_map.items():
        if len(indices) == 0:
            continue
        valid = indices[indices < len(probs)]
        if len(valid) == 0:
            continue
        cp = probs[valid]
        mask = cp >= threshold
        for li in np.where(mask)[0]:
            gi = int(valid[li])
            name = labels.names[gi]
            if name:
                by_cat[category].append((name, float(cp[li])))

    flat: list[dict[str, Any]] = []
    for cat, pairs in by_cat.items():
        for tag, score in sorted(pairs, key=lambda x: x[1], reverse=True):
            flat.append({"tag": tag.replace("_", " "), "score": score, "category": cat})
    flat.sort(key=lambda x: x["score"], reverse=True)
    return flat[:max_tags]


class ClTaggerSession:
    def __init__(
        self,
        *,
        cache_dir: Path,
        repo_id: str = DEFAULT_REPO,
        gen_threshold: float = 0.35,
        char_threshold: float = 0.85,
        max_tags: int = 64,
        download: bool = True,
        cuda_device_id: int | None = None,
    ):
        self.gen_threshold = gen_threshold
        self.char_threshold = char_threshold
        self.max_tags = max_tags
        self._session = None
        self._labels: LabelData | None = None
        self._input_name: str | None = None
        self._output_name: str | None = None

        onnx_path = cache_dir / "model.onnx"
        mapping_path = cache_dir / "tag_mapping.json"
        if download or not onnx_path.is_file():
            from huggingface_hub import hf_hub_download

            cache_dir.mkdir(parents=True, exist_ok=True)
            onnx_path = Path(
                hf_hub_download(
                    repo_id=repo_id,
                    filename=DEFAULT_ONNX,
                    cache_dir=str(cache_dir),
                )
            )
            mapping_path = Path(
                hf_hub_download(
                    repo_id=repo_id,
                    filename=DEFAULT_MAPPING,
                    cache_dir=str(cache_dir),
                )
            )

        import onnxruntime as ort

        providers = ort.get_available_providers()
        use: list[str | tuple[str, dict[str, Any]]] = []
        if "CUDAExecutionProvider" in providers:
            opts: dict[str, Any] = {}
            if cuda_device_id is not None:
                opts["device_id"] = int(cuda_device_id)
            use.append(("CUDAExecutionProvider", opts) if opts else "CUDAExecutionProvider")
        use.append("CPUExecutionProvider")
        self._session = ort.InferenceSession(str(onnx_path), providers=use)
        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name
        self._labels = load_tag_mapping(mapping_path)
        self.provider = self._session.get_providers()[0]

    def tag_path(self, path: Path) -> list[dict[str, Any]]:
        assert self._session and self._labels and self._input_name and self._output_name
        with Image.open(path) as img:
            tensor = preprocess_image(img)
        outputs = self._session.run([self._output_name], {self._input_name: tensor})[0]
        outputs = np.nan_to_num(outputs, nan=0.0, posinf=1.0, neginf=0.0)
        probs = _stable_sigmoid(outputs[0])
        return get_tags(probs, self._labels, self.gen_threshold, self.char_threshold, self.max_tags)
