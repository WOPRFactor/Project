"""Render compartido del tablero (árbol + timeline).

Cada mutación recalcula todo el cronograma y devuelve este parcial, así la vista
siempre refleja el estado real sin recargar la página.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from ..services import projects as projects_service
from ..services import tasks as tasks_service
from ..services import vista as vista_service
from ..templating import templates


def contexto(session: Session, project_id: int) -> dict:
    proyecto = projects_service.obtener(session, project_id)
    datos = vista_service.armar(session, project_id)
    return {
        "proyecto": proyecto,
        "filas": datos.filas,
        "grilla": datos.grilla,
        "columna_hoy": datos.columna_hoy,
        "error_motor": datos.error,
        "hojas": [f.tarea for f in datos.filas if not f.es_resumen],
        "todas": tasks_service.arbol(session, project_id),
    }


def render(
    request: Request,
    session: Session,
    project_id: int,
    aviso: str | None = None,
) -> HTMLResponse:
    datos = contexto(session, project_id)
    datos["aviso"] = aviso
    return templates.TemplateResponse(request, "partials/tablero.html", datos)
