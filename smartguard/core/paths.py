"""Rutas de recursos del paquete y de los datos del usuario."""

import os
from pathlib import Path

from platformdirs import user_data_dir

PACKAGE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = PACKAGE_DIR / "assets"
DEMO_VIDEO = PACKAGE_DIR.parent / "samples" / "demo.mp4"


def asset(*parts: str) -> str:
    return str(ASSETS_DIR.joinpath(*parts))


def data_dir() -> Path:
    """Carpeta de datos (base de datos, capturas, modelos). ``SMARTGUARD_HOME`` la reemplaza."""
    path = Path(os.environ.get("SMARTGUARD_HOME") or user_data_dir("SmartGuard", appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir() -> Path:
    return data_dir() / "models"
