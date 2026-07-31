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


# El año de WarGames: distintivo, fácil de acordarse y ningún software lo pisa.
PUERTO_POR_DEFECTO = 1983


def puerto() -> int:
    """Puerto del arranque propio (`python -m app`), desde `WOPR_PORT`.

    Se valida acá y no al importar el módulo: un WOPR_PORT roto tiene que frenar
    el arranque con un mensaje claro, no romper cualquier import de la app (los
    tests, o levantar con el CLI de uvicorn, que ni lo usa).
    """
    crudo = os.getenv("WOPR_PORT", "").strip()
    if not crudo:
        return PUERTO_POR_DEFECTO
    if not crudo.isdigit() or not 1 <= int(crudo) <= 65535:
        raise SystemExit(
            f"WOPR_PORT={crudo!r} no sirve: tiene que ser un entero entre 1 y 65535 "
            f"(ej. {PUERTO_POR_DEFECTO})"
        )
    return int(crudo)


@dataclass(frozen=True)
class Settings:
    # El host no es configurable a propósito: 127.0.0.1 está clavado en __main__.py.
    db_path: str = os.getenv("WOPR_DB", str(RAIZ / "wopr-proyectos.db"))
    debug: bool = _bool_env("WOPR_DEBUG", False)

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
