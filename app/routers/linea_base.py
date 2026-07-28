"""Congelar la línea base y elegir cuál está vigente."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from ..db import get_session
from ..services import linea_base as linea_base_service
from ..services import projects as projects_service
from ..services import vista as vista_service
from ..services.linea_base import LineaBaseInvalida
from ..templating import templates
from ._tablero import Mirada, mirada_form, render

router = APIRouter(prefix="/proyectos/{project_id}/base")


@router.get("", response_class=HTMLResponse)
def panel(
    project_id: int, request: Request, aviso: str = "", session: Session = Depends(get_session)
) -> HTMLResponse:
    proyecto = projects_service.obtener(session, project_id)
    if proyecto is None:
        return templates.TemplateResponse(
            request, "error.html", {"mensaje": "Ese proyecto no existe"}, status_code=404
        )
    datos = vista_service.armar(session, project_id)
    return templates.TemplateResponse(request, "base/lista.html", {
        "proyecto": proyecto,
        "lineas": linea_base_service.listar(session, project_id),
        "vigente": linea_base_service.vigente(session, project_id),
        "desvio_ambito": linea_base_service.desvio_por_ambito(session, project_id, datos),
        "niveles_abiertos": datos.niveles_abiertos,
        "aviso": aviso or None,
    })


@router.post("/congelar", response_class=HTMLResponse)
def congelar(
    project_id: int,
    request: Request,
    nombre: str = Form(""),
    nota: str = Form(""),
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    datos = vista_service.armar(session, project_id)
    try:
        linea = linea_base_service.congelar(session, project_id, datos, nombre, nota)
    except LineaBaseInvalida as error:
        return render(request, session, project_id, aviso=str(error), mirada=mirada)
    return render(
        request, session, project_id, mirada=mirada,
        aviso=f"Línea base «{linea.nombre}» congelada: desde ahora el desvío se mide contra esto.",
    )


@router.post("/{linea_id}/vigente")
def marcar_vigente(
    project_id: int, linea_id: int, session: Session = Depends(get_session)
) -> RedirectResponse:
    if not _del_proyecto(session, project_id, linea_id):
        return _volver(project_id, "Esa línea base no es de este proyecto")
    linea_base_service.marcar_vigente(session, project_id, linea_id)
    return _volver(project_id, "")


@router.post("/{linea_id}/eliminar")
def eliminar(
    project_id: int, linea_id: int, session: Session = Depends(get_session)
) -> RedirectResponse:
    if not _del_proyecto(session, project_id, linea_id):
        return _volver(project_id, "Esa línea base no es de este proyecto")
    linea_base_service.eliminar(session, linea_id)
    return _volver(project_id, "Línea base borrada")


def _del_proyecto(session: Session, project_id: int, linea_id: int) -> bool:
    return any(l.id == linea_id for l in linea_base_service.listar(session, project_id))


def _volver(project_id: int, aviso: str) -> RedirectResponse:
    destino = f"/proyectos/{project_id}/base"
    if aviso:
        destino += "?" + urlencode({"aviso": aviso})
    return RedirectResponse(destino, status_code=303)
