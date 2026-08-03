"""HTML → PDF con el Chrome del sistema. No sabe qué es un proyecto.

Se eligió Chrome y no una librería de PDF porque **el Gantt ya es HTML y CSS**: cualquier
otra vía obliga a redibujarlo, y a partir de ahí el papel y la pantalla empiezan a
separarse. Imprimiendo la misma plantilla, lo que ves es lo que sale.

El HTML que entra tiene que ser **autocontenido** (el CSS embebido en un `<style>`): se
imprime desde un archivo temporal con `file://`, donde una ruta como `/static/estilo.css`
no resuelve y el PDF saldría sin estilos.

Dos precauciones que no son opcionales:

- **Perfil aparte** (`--user-data-dir`). Sin esto, Chrome reusa la instancia que el
  usuario ya tiene abierta y el `--print-to-pdf` no pasa nunca.
- **Timeout.** Un Chrome colgado no puede colgar un request de la app.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

# Lo que se espera a Chrome antes de darlo por perdido. Un informe con Gantt largo
# tarda un par de segundos; 60 es holgado y a la vez acotado.
ESPERA_SEGUNDOS = 60

# Cuánto se le da a la página para terminar de pintar antes de imprimir. El Gantt es
# CSS puro, así que no hay red ni scripts que esperar.
TIEMPO_VIRTUAL_MS = 3000

_CANDIDATOS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


class PdfNoDisponible(Exception):
    """No hay con qué generar el PDF; el mensaje se le muestra al usuario."""


def navegador() -> str | None:
    """Con qué se va a imprimir, o None si no hay nada. `WOPR_CHROME` manda."""
    elegido = os.getenv("WOPR_CHROME", "").strip()
    if elegido:
        return elegido if Path(elegido).is_file() else None
    for ruta in _CANDIDATOS:
        if Path(ruta).is_file():
            return ruta
    # En Linux/macOS o con Chrome en el PATH.
    for nombre in ("chrome", "google-chrome", "chromium", "msedge"):
        encontrado = shutil.which(nombre)
        if encontrado:
            return encontrado
    return None


def hay_como_imprimir() -> bool:
    """Para que la UI no ofrezca un botón que va a fallar."""
    return navegador() is not None


def desde_html(html: str, horizontal: bool = False) -> bytes:
    """Imprime el HTML y devuelve los bytes del PDF.

    La orientación no se pasa por línea de comando a propósito: Chrome respeta el
    `@page` del CSS, así que el documento decide cómo se imprime y queda una sola
    fuente de verdad. El parámetro existe solo para dejarlo dicho en el log del futuro.
    """
    ejecutable = navegador()
    if ejecutable is None:
        raise PdfNoDisponible(
            "Para generar el PDF hace falta Google Chrome (o Edge) instalado. "
            "Si lo tenés en otra ruta, indicala en la variable WOPR_CHROME."
        )

    with tempfile.TemporaryDirectory(prefix="wopr-pdf-") as carpeta:
        base = Path(carpeta)
        entrada = base / "documento.html"
        salida = base / "documento.pdf"
        entrada.write_text(html, encoding="utf-8")

        comando = [
            ejecutable,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            # Perfil descartable: no toca ni usa el Chrome abierto del usuario.
            f"--user-data-dir={base / 'perfil'}",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            f"--virtual-time-budget={TIEMPO_VIRTUAL_MS}",
            f"--print-to-pdf={salida}",
            entrada.as_uri(),
        ]
        try:
            resultado = subprocess.run(
                comando, capture_output=True, timeout=ESPERA_SEGUNDOS, check=False
            )
        except subprocess.TimeoutExpired as error:
            raise PdfNoDisponible(
                "El navegador tardó demasiado en generar el PDF y lo corté. "
                "Probá de nuevo; si sigue, el proyecto puede ser muy grande."
            ) from error

        if not salida.is_file() or salida.stat().st_size == 0:
            detalle = (resultado.stderr or b"").decode("utf-8", "replace").strip()
            raise PdfNoDisponible(
                "El navegador no pudo generar el PDF"
                + (f": {detalle.splitlines()[-1]}" if detalle else ".")
            )
        return salida.read_bytes()
