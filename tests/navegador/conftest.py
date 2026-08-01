"""Tests con navegador real: opcionales a propósito.

Corren solo si Playwright está instalado (grupo `navegador` de pyproject:
`uv sync --group navegador`); sin él, pytest saltea la carpeta entera y la suite
normal no cambia. Usan el Chrome del sistema (`channel="chrome"`): no descargan
ningún navegador.

El server corre en un **subproceso** con su propia DB temporal: importar `app.db`
acá adentro compartiría el engine (y la base) con el resto de la suite.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip(
    "playwright", reason="tests de navegador: instalá el grupo `navegador`"
)

from playwright.sync_api import sync_playwright  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]

_SEMILLA = """
from datetime import date
from pathlib import Path
from sqlmodel import Session
from app.db import engine, init_db
from app.services import importar_aplicar, importar_excel

init_db()
contenido = (Path("tests") / "fixtures" / "gantt-traspaso.xlsx").read_bytes()
importacion = importar_excel.leer(contenido)
with Session(engine) as session:
    importar_aplicar.aplicar(session, "Navegador", date(2026, 10, 5), importacion)
"""


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def servidor(tmp_path_factory):
    """La app en un subproceso, con una DB temporal sembrada. Devuelve la URL base."""
    db = tmp_path_factory.mktemp("navegador") / "prueba.db"
    entorno = os.environ | {"WOPR_DB": str(db)}
    subprocess.run(
        [sys.executable, "-c", _SEMILLA],
        cwd=RAIZ, env=entorno, check=True, capture_output=True,
    )

    puerto = _puerto_libre()
    proceso = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(puerto)],
        cwd=RAIZ, env=entorno,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{puerto}"
    try:
        _esperar_salud(url, proceso)
        yield url
    finally:
        proceso.terminate()
        try:
            proceso.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proceso.kill()


def _esperar_salud(url: str, proceso) -> None:
    for _ in range(60):
        if proceso.poll() is not None:
            pytest.fail("el server de prueba murió al arrancar")
        try:
            with urllib.request.urlopen(f"{url}/salud", timeout=1):
                return
        except OSError:
            time.sleep(0.5)
    pytest.fail("el server de prueba nunca respondió /salud")


@pytest.fixture(scope="session")
def navegador():
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:  # noqa: BLE001 — sin Chrome instalado no hay qué testear
            pytest.skip("no hay Chrome del sistema para Playwright")
        yield browser
        browser.close()


@pytest.fixture
def pagina(navegador, servidor):
    """Una página nueva por test, con la URL base y recolector de errores.

    `pagina.errores` junta errores de consola, excepciones JS y respuestas >= 400:
    cada test afirma al final que quedó vacío.
    """
    contexto = navegador.new_context(viewport={"width": 1600, "height": 900})
    page = contexto.new_page()
    page.base = servidor
    page.errores = []
    page.on(
        "console",
        lambda m: page.errores.append(f"console: {m.text}")
        if m.type == "error"
        else None,
    )
    page.on("pageerror", lambda e: page.errores.append(f"pageerror: {e}"))
    page.on(
        "response",
        lambda r: page.errores.append(f"HTTP {r.status} {r.url}")
        if r.status >= 400
        else None,
    )
    page.on("dialog", lambda d: d.accept())
    yield page
    contexto.close()
