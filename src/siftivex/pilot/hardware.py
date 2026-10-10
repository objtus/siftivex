"""GPU / runtime metadata for pilot JSON reports."""

from __future__ import annotations

import platform
import subprocess
from contextlib import contextmanager
from typing import Any, Iterator


def collect_hardware() -> dict[str, Any]:
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    try:
        import torch

        info["torch"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            info["cuda_version"] = torch.version.cuda
            info["cuda_device_count"] = torch.cuda.device_count()
            gpus: list[dict[str, Any]] = []
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                gpus.append(
                    {
                        "index": i,
                        "name": torch.cuda.get_device_name(i),
                        "vram_mb": int(getattr(props, "total_memory", 0) // (1024 * 1024)),
                    }
                )
            info["gpus"] = gpus
            info["gpu_name"] = gpus[0]["name"] if gpus else None
            info["gpu_vram_mb"] = gpus[0]["vram_mb"] if gpus else None
    except Exception as exc:  # noqa: BLE001
        info["torch_error"] = str(exc)

    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            lines = out.stdout.strip().splitlines()
            info["nvidia_smi"] = lines[0] if len(lines) == 1 else lines
    except Exception as exc:  # noqa: BLE001
        info["nvidia_smi_error"] = str(exc)

    return info


@contextmanager
def track_peak_vram_mb() -> Iterator[dict[str, int | None]]:
    peak: dict[str, int | None] = {"peak_vram_mb": None}
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        yield peak
        return

    try:
        yield peak
    finally:
        try:
            import torch

            if torch.cuda.is_available():
                peak["peak_vram_mb"] = int(torch.cuda.max_memory_allocated() // (1024 * 1024))
        except Exception:
            pass
