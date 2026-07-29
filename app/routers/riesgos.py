"""Panel de riesgos y cuadrante. HTTP puro: parsear, llamar al service, renderizar."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlmodel import Session

from ..db import get_session
from ..models import ETIQUETA_ESTADO_RIESGO, ETIQUETA_RESPUESTA
from ..schemas import RiesgoIn
from ..services import matriz as matriz_service
from ..services import projects as projects_service
from ..services import riesgos as riesgos_service
from ..services.riesgos import RiesgoInvalido
from ..templating import templates

router = APIRouter(prefix="/proyectos/{project_id}/riesgos")


def formulario(
    descripcion: str = Form(""),
    probabilidad: str = Form("3"),
    impacto: str = Form("3"),
    mitigacion: str = Form(""),
    responsable: str = Form(""),
    estado: str = Form("abierto"),
    respuesta: str = Form("sin_definir"),
    probabilidad_residual: str = Form(""),
    impacto_residual: str = Form(""),
    disparador: str = Form(""),
    revisar_el: str = Form(""),
    mitigacion_task_id: str = Form(""),
) -> tuple:
    """El formulario del registro, ya validado. Devuelve `(datos, error)`.

    Alta y edición mandan exactamente los mismos campos, así que se leen en un solo
    lugar; si no, cada campo nuevo hay que acordarse de agregarlo dos veces.
    """
    try:
        return RiesgoIn(
            descripcion=descripcion,
            probabilidad=_entero(probabilidad, 3),
            impacto=_entero(impacto, 3),
            mitigacion=mitigacion,
            responsable=responsable,
            estado=estado,
            respuesta=respuesta,
            probabilidad_residual=_opcional(probabilidad_residual),
            impacto_residual=_opcional(impacto_residual),
            disparador=disparador,
            revisar_el=_fecha(revisar_el),
            mitigacion_task_id=_opcional(mitigacion_task_id),
        ), ""
    except ValidationError as error:
        return None, "; ".join(e.get("msg", "dato inválido") for e in error.errors())
    except ValueError as error:
        return None, str(error)


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
        "respuestas": ETIQUETA_RESPUESTA,
        "etiqueta_zona": matriz_service.ETIQUETA_ZONA,
        "etiqueta_probabilidad": matriz_service.ETIQUETA_PROBABILIDAD,
        "etiqueta_impacto": matriz_service.ETIQUETA_IMPACTO,
        "aviso": aviso or None,
    })


@router.post("")
def crear(
    project_id: int,
    task_id: str = Form(""),
    entrada: tuple = Depends(formulario),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    datos, error = entrada
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
    entrada: tuple = Depends(formulario),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if not _del_proyecto(session, project_id, riesgo_id):
        return _volver(project_id, "Ese riesgo no es de este proyecto")
    datos, error = entrada
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


def _entero(crudo: str, default: int) -> int:
    return int(crudo) if crudo.strip().isdigit() else default


def _opcional(crudo: str) -> int | None:
    """Vacío es un valor: «todavía no se estimó», que no es lo mismo que un número."""
    return int(crudo) if crudo.strip().isdigit() else None


def _fecha(crudo: str) -> date | None:
    if not crudo.strip():
        return None
    try:
        return date.fromisoformat(crudo.strip())
    except ValueError:
        raise ValueError("La fecha de revisión no es válida") from None


def _del_proyecto(session: Session, project_id: int, riesgo_id: int) -> bool:
    riesgo = riesgos_service.obtener(session, riesgo_id)
    return riesgo is not None and riesgo.project_id == project_id


def _volver(project_id: int, aviso: str) -> RedirectResponse:
    destino = f"/proyectos/{project_id}/riesgos"
    if aviso:
        destino += "?" + urlencode({"aviso": aviso})
    return RedirectResponse(destino, status_code=303)
