"""Arranque propio: `python -m app` levanta la app en el puerto configurado.

El host queda clavado en 127.0.0.1 desde el código: la regla de seguridad de
CLAUDE.md deja de depender del default de uvicorn o de cómo se invoque. El
CLI de uvicorn sigue funcionando igual para quien lo prefiera.
"""

from __future__ import annotations

import uvicorn

from .config import puerto


def main() -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=puerto(), reload=True)


if __name__ == "__main__":
    main()
