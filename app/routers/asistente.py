"""El panel del asistente. HTTP puro: parsear, llamar al service, renderizar.

Dos rutas con papeles distintos: `preguntar` NUNCA escribe (devuelve análisis y
acciones propuestas en un parcial chico, sin repintar la grilla); `aplicar` es
la confirmación explícita del usuario — solo ahí se ejecutan las acciones, y el
tablero entero se re-renderiza con el cronograma recalculado.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from ..auth.dependencias import exige_usuario
from ..db import get_session
from ..services import asistente as asistente_service
from ..services import asistente_acciones
from ..services.asistente import AsistenteNoDisponible
from ..templating import templates
from ._tablero import Mirada, mirada_form, render

router = APIRouter(prefix="/proyectos/{project_id}", dependencies=[Depends(exige_usuario)])


@router.post("/asistente", response_class=HTMLResponse)
def preguntar(
    project_id: int,
    request: Request,
    pregunta: str = Form(""),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        consulta = asistente_service.consultar(session, project_id, pregunta)
        contexto = {
            "respuesta": consulta.analisis,
            "acciones": consulta.acciones,
            "acciones_json": asistente_acciones.a_json(consulta.acciones),
            "avisos": consulta.avisos,
            "error": None,
            "proyecto_id": project_id,
        }
    except AsistenteNoDisponible as error:
        contexto = {
            "respuesta": None, "acciones": [], "acciones_json": "",
            "avisos": [], "error": str(error), "proyecto_id": project_id,
        }
    return templates.TemplateResponse(request, "partials/asistente.html", contexto)


@router.post("/asistente/aplicar", response_class=HTMLResponse)
def aplicar(
    project_id: int,
    request: Request,
    carga: str = Form(""),
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """La confirmación. La carga vuelve del navegador: se re-valida desde cero."""
    acciones, avisos = asistente_acciones.desde_json(carga)
    if acciones:
        avisos += asistente_acciones.aplicar(session, project_id, acciones)
        partes = [f"{len(acciones)} cambios del asistente aplicados"] + avisos
        aviso = "; ".join(partes)
    else:
        aviso = "; ".join(avisos) or "No había acciones para aplicar"
    return render(request, session, project_id, aviso=aviso, mirada=mirada)
