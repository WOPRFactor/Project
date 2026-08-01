"""El panel del asistente. HTTP puro: parsear el pedido, llamar al service, renderizar.

Devuelve un parcial chico (solo la respuesta), no el tablero: preguntar no debe
recalcular ni repintar la grilla.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from ..db import get_session
from ..services import asistente as asistente_service
from ..services.asistente import AsistenteNoDisponible
from ..templating import templates

router = APIRouter(prefix="/proyectos/{project_id}")


@router.post("/asistente", response_class=HTMLResponse)
def preguntar(
    project_id: int,
    request: Request,
    pregunta: str = Form(""),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        respuesta = asistente_service.analizar(session, project_id, pregunta)
        contexto = {"respuesta": respuesta, "error": None}
    except AsistenteNoDisponible as error:
        contexto = {"respuesta": None, "error": str(error)}
    return templates.TemplateResponse(request, "partials/asistente.html", contexto)
