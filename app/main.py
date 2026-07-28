"""Wiring de la app: monta routers, estáticos y manejadores de error.

Sin lógica de negocio. Los errores llegan al navegador como mensaje claro, nunca
como stack trace.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import RAIZ, settings
from .db import init_db
from .routers import (
    carga, estados, export, importar, informe, linea_base, projects, riesgos, tasks,
)
from .templating import templates

log = logging.getLogger("wopr")

@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="WOPR Proyectos",
    debug=settings.debug,
    docs_url=None,
    redoc_url=None,
    lifespan=ciclo_de_vida,
)
app.mount("/static", StaticFiles(directory=RAIZ / "static"), name="static")
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(estados.router)
app.include_router(export.router)
app.include_router(importar.router)
app.include_router(riesgos.router)
app.include_router(carga.router)
app.include_router(linea_base.router)
app.include_router(informe.router)


@app.get("/salud", include_in_schema=False)
def salud() -> dict[str, str]:
    return {"estado": "ok"}


@app.exception_handler(ValidationError)
async def error_de_validacion(request: Request, exc: ValidationError) -> HTMLResponse:
    detalles = "; ".join(e.get("msg", "dato inválido") for e in exc.errors())
    return _pagina_error(request, f"Revisá los datos: {detalles}", 400)


@app.exception_handler(500)
async def error_interno(request: Request, exc: Exception) -> HTMLResponse:
    log.exception("Error interno procesando %s", request.url.path)
    return _pagina_error(request, "Algo se rompió de este lado. Revisá el log local.", 500)


def _pagina_error(request: Request, mensaje: str, codigo: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "error.html", {"mensaje": mensaje}, status_code=codigo
    )
