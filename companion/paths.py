"""Local storage locations. Everything stays under one user-only directory."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    configured = os.environ.get("EVERYTHING_PROXY_HOME")
    if configured:
        path = Path(configured).expanduser()
    else:
        path = Path.home() / "Library" / "Application Support" / "everything-proxy"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(path, 0o700)
    return path


def database_path() -> Path:
    return data_dir() / "gateway.sqlite3"


MODEL_DIR = Path.home() / ".cache" / "everything-proxy" / "models"
MLX_PYTHON = Path.home() / ".cache" / "everything-proxy" / "venvs" / "bonsai-mlx" / "bin" / "python"
