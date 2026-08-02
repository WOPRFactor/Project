"""Configuración por variables de entorno, con defaults seguros para uso local."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _cargar_env() -> None:
    """Carga `RAIZ/.env` al entorno, sin pisar lo ya definido afuera.

    Sin dependencia externa a propósito: el formato es `CLAVE=valor` por línea,
    `#` comenta. Acá viven los secretos (GROQ_API_KEY) — el archivo está en
    .gitignore y jamás se commitea.
    """
    archivo = RAIZ / ".env"
    if not archivo.exists():
        return
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env()


def _bool_env(nombre: str, default: bool = False) -> bool:
    valor = os.getenv(nombre)
    if valor is None:
        return default
    return valor.strip().lower() in {"1", "true", "yes", "si", "sí"}


# El año de WarGames: distintivo, fácil de acordarse y ningún software lo pisa.
PUERTO_POR_DEFECTO = 1983

# El modelo de Groq para el asistente. Configurable porque el catálogo de Groq
# rota seguido; este default es sólido y de capa gratuita.
MODELO_IA_POR_DEFECTO = "llama-3.3-70b-versatile"


# Solo para desarrollo local: en modo no-debug la app se niega a arrancar con esto.
_SECRET_DE_DESARROLLO = "wopr-desarrollo-inseguro"


def groq_api_key() -> str:
    """Perezosa a propósito: los tests la cambian por entorno sin re-importar."""
    return os.getenv("GROQ_API_KEY", "").strip()


def secret_key() -> str:
    """Secreto que firma los tokens CSRF. Obligatorio fuera de modo debug."""
    valor = os.getenv("WOPR_SECRET_KEY", "").strip()
    if valor and valor != _SECRET_DE_DESARROLLO:
        return valor
    if settings.debug:
        return _SECRET_DE_DESARROLLO
    raise SystemExit(
        "Falta WOPR_SECRET_KEY (o es el valor de desarrollo). Generá uno con:\n"
        "  python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
        "y cargalo en el .env de la raíz. Sin eso la app no arranca fuera de debug."
    )


def ia_modelo() -> str:
    return os.getenv("WOPR_IA_MODELO", "").strip() or MODELO_IA_POR_DEFECTO


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
    # Cookie de sesión con el flag `Secure`. En localhost sobre HTTP tiene que ir
    # apagada (el navegador la descartaría); detrás del proxy TLS de la Fase 13 va
    # prendida, y ahí la app ve http porque el TLS lo termina el proxy — por eso es
    # una variable explícita y no algo deducido del esquema del request.
    cookie_segura: bool = _bool_env("WOPR_COOKIE_SEGURA", False)

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
