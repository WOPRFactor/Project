"""Panel de riesgos y cuadrante. HTTP puro: parsear, llamar al service, renderizar."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlmodel import Session

from ..auth.dependencias import exige_usuario
from ..db import get_session
from ..models import ETIQUETA_ESTADO_RIESGO
from ..schemas import RiesgoIn
from ..services import matriz as matriz_service
from ..services import projects as projects_service
from ..services import riesgos as riesgos_service
from ..services.riesgos import RiesgoInvalido
from ..templating import templates

router = APIRouter(prefix="/proyectos/{project_id}/riesgos", dependencies=[Depends(exige_usuario)])


@router.get("", response_class=HTMLResponse)
def panel(
    project_id: int, request: Request, aviso: str = "", session: Session = Depends(get_session)
) -> HTMLResponse:
    proyecto = projects_service.obtener(session, project_id)
    if proyecto is None:
        return templates.TemplateResponse(
            request, "error.html", {"mensaje": "Ese proyecto no existe"}, status_code=404
        )
    return templates.TemplateResponse(request, "riesgos/panel.html", {
        "proyecto": proyecto,
        "panel": riesgos_service.panel(session, project_id),
        "estados_riesgo": ETIQUETA_ESTADO_RIESGO,
        "etiqueta_zona": matriz_service.ETIQUETA_ZONA,
        "etiqueta_probabilidad": matriz_service.ETIQUETA_PROBABILIDAD,
        "etiqueta_impacto": matriz_service.ETIQUETA_IMPACTO,
        "aviso": aviso or None,
    })


@router.post("")
def crear(
    project_id: int,
    descripcion: str = Form(""),
    probabilidad: str = Form("3"),
    impacto: str = Form("3"),
    mitigacion: str = Form(""),
    responsable: str = Form(""),
    estado: str = Form("abierto"),
    task_id: str = Form(""),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    datos, error = _leer(descripcion, probabilidad, impacto, mitigacion, responsable, estado)
    if error:
        return _volver(project_id, error)
    try:
        riesgos_service.crear(
            session, project_id, datos,
            int(task_id) if task_id.strip().isdigit() else None,
        )
    except RiesgoInvalido as problema:
        return _volver(project_id, str(problema))
    return _volver(project_id, "")


@router.post("/{riesgo_id}")
def actualizar(
    project_id: int,
    riesgo_id: int,
    descripcion: str = Form(""),
    probabilidad: str = Form("3"),
    impacto: str = Form("3"),
    mitigacion: str = Form(""),
    responsable: str = Form(""),
    estado: str = Form("abierto"),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if not _del_proyecto(session, project_id, riesgo_id):
        return _volver(project_id, "Ese riesgo no es de este proyecto")
    datos, error = _leer(descripcion, probabilidad, impacto, mitigacion, responsable, estado)
    if error:
        return _volver(project_id, error)
    try:
        riesgos_service.actualizar(session, riesgo_id, datos)
    except RiesgoInvalido as problema:
        return _volver(project_id, str(problema))
    return _volver(project_id, "")


@router.post("/{riesgo_id}/eliminar")
def eliminar(
    project_id: int, riesgo_id: int, session: Session = Depends(get_session)
) -> RedirectResponse:
    if not _del_proyecto(session, project_id, riesgo_id):
        return _volver(project_id, "Ese riesgo no es de este proyecto")
    riesgos_service.eliminar(session, riesgo_id)
    return _volver(project_id, "Riesgo borrado")


def _leer(descripcion, probabilidad, impacto, mitigacion, responsable, estado):
    try:
        return RiesgoIn(
            descripcion=descripcion,
            probabilidad=_entero(probabilidad, 3),
            impacto=_entero(impacto, 3),
            mitigacion=mitigacion,
            responsable=responsable,
            estado=estado,
        ), ""
    except ValidationError as error:
        return None, "; ".join(e.get("msg", "dato inválido") for e in error.errors())


def _entero(crudo: str, default: int) -> int:
    return int(crudo) if crudo.strip().isdigit() else default


def _del_proyecto(session: Session, project_id: int, riesgo_id: int) -> bool:
    riesgo = riesgos_service.obtener(session, riesgo_id)
    return riesgo is not None and riesgo.project_id == project_id


def _volver(project_id: int, aviso: str) -> RedirectResponse:
    destino = f"/proyectos/{project_id}/riesgos"
    if aviso:
        destino += "?" + urlencode({"aviso": aviso})
    return RedirectResponse(destino, status_code=303)
