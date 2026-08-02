"""Wiring de la app: monta routers, estáticos y manejadores de error.

Sin lógica de negocio. Los errores llegan al navegador como mensaje claro, nunca
como stack trace. Desde la Fase 10 la app tiene puerta: todo lo que no sea el
login o los estáticos exige sesión, y toda mutación exige token CSRF.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .auth import csrf as csrf_service
from .auth import sesion as sesion_service
from .auth.dependencias import RedirigirALogin, respuesta_sin_sesion
from .auth.middleware import ExigeCsrf
from .config import RAIZ, settings
from .db import init_db
from .routers import (
    admin, asistente, auth, carga, equipo, estados, export, importar, informe,
    linea_base, projects, riesgos, tasks,
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
app.add_middleware(ExigeCsrf)
app.mount("/static", StaticFiles(directory=RAIZ / "static"), name="static")
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(estados.router)
app.include_router(export.router)
app.include_router(importar.router)
app.include_router(riesgos.router)
app.include_router(carga.router)
app.include_router(linea_base.router)
app.include_router(informe.router)
app.include_router(equipo.router)
app.include_router(asistente.router)


@app.middleware("http")
async def contexto_de_plantillas(request: Request, call_next):
    """Deja el token CSRF (y el usuario, si lo puso una dependencia) a mano en Jinja."""
    token = request.cookies.get(sesion_service.COOKIE, "")
    request.state.csrf_token = csrf_service.token_de(token)
    return await call_next(request)


@app.get("/salud", include_in_schema=False)
def salud() -> dict[str, str]:
    return {"estado": "ok"}


@app.exception_handler(RedirigirALogin)
async def sin_sesion(request: Request, exc: RedirigirALogin):
    return respuesta_sin_sesion(request, exc.destino)


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
