"""NVIDIA shared libraries + optional GPU pinning for ONNX / batch scripts."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


def _venv_nvidia_lib_dirs() -> list[Path]:
    base = Path(sys.prefix) / "lib"
    py_dirs = sorted(base.glob("python*/site-packages/nvidia"))
    if not py_dirs:
        return []
    site = py_dirs[-1].parent
    candidates = [
        site / "nvidia/cudnn/lib",
        site / "nvidia/cu13/lib",
        site / "nvidia/cublas/lib",
        site / "nvidia/cuda_runtime/lib",
    ]
    return [p for p in candidates if p.is_dir()]


def _ensure_cudnn_soname(cudnn_dir: Path) -> None:
    """ORT looks for libcudnn.so; pip ships libcudnn.so.9."""
    target = cudnn_dir / "libcudnn.so"
    if target.exists():
        return
    versioned = next(cudnn_dir.glob("libcudnn.so.*"), None)
    if versioned is None or not os.access(cudnn_dir, os.W_OK):
        return
    try:
        target.symlink_to(versioned.name)
    except OSError:
        pass


def _preload_shared_libs(dirs: list[Path]) -> None:
    """Load cuDNN/CUDA libs before onnxruntime (LD_LIBRARY_PATH alone is too late)."""
    flags = getattr(ctypes, "RTLD_GLOBAL", 0)
    for lib_dir in dirs:
        for pattern in (
            "libcudnn.so*",
            "libcublas.so*",
            "libcublasLt.so*",
            "libcudart.so*",
        ):
            for path in sorted(lib_dir.glob(pattern)):
                if path.is_symlink() or path.suffix == ".so" or ".so." in path.name:
                    try:
                        ctypes.CDLL(str(path), mode=flags)
                    except OSError:
                        pass


def configure_nvidia_libs() -> list[str]:
    """Prepare venv NVIDIA libs. Call before importing onnxruntime."""
    dirs = _venv_nvidia_lib_dirs()
    for d in dirs:
        if "cudnn" in str(d):
            _ensure_cudnn_soname(d)
    if dirs:
        extra = ":".join(str(d) for d in dirs)
        prev = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = f"{extra}:{prev}" if prev else extra
        _preload_shared_libs(dirs)
    return [str(d) for d in dirs]


def pin_visible_cuda_devices(device_indices: str | int | None) -> None:
    """Set CUDA_VISIBLE_DEVICES (e.g. 2 → tagger uses physical 2070 SUPER)."""
    if device_indices is None:
        return
    os.environ["CUDA_VISIBLE_DEVICES"] = str(device_indices)


def apply_d1_gpu_config(cfg: dict) -> None:
    """Pin d1 (PyTorch) when `cuda_visible_devices` is set; else use `device: cuda:N`."""
    configure_nvidia_libs()
    visible = cfg.get("cuda_visible_devices")
    if visible is not None:
        pin_visible_cuda_devices(visible)


def apply_tagger_gpu_config(cfg: dict) -> None:
    """From model_stack_pilot.yaml `tagger` section."""
    configure_nvidia_libs()
    visible = cfg.get("cuda_visible_devices")
    if visible is not None:
        pin_visible_cuda_devices(visible)
        return
    # Legacy: cuda_device_id alone — pin ORT to that physical GPU when NVML is flaky.
    cuda_id = cfg.get("cuda_device_id")
    if cuda_id is not None:
        pin_visible_cuda_devices(int(cuda_id))
