"""Configuración por variables de entorno, con defaults seguros para uso local."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _bool_env(nombre: str, default: bool = False) -> bool:
    valor = os.getenv(nombre)
    if valor is None:
        return default
    return valor.strip().lower() in {"1", "true", "yes", "si", "sí"}


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("WOPR_HOST", "127.0.0.1")
    port: int = int(os.getenv("WOPR_PORT", "8000"))
    db_path: str = os.getenv("WOPR_DB", str(RAIZ / "wopr-proyectos.db"))
    debug: bool = _bool_env("WOPR_DEBUG", False)

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
