"""Quiénes participan del proyecto. Solo el dueño administra esta pantalla."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from ..auth.dependencias import Acceso, exige_duenio, exige_lector
from ..db import get_session
from ..models_auth import DESCRIPCION_ROL, ETIQUETA_ROL, Rol
from ..services import miembros as miembros_service
from ..services import usuarios as usuarios_service
from ..services.miembros import MiembroInvalido
from ..templating import templates

router = APIRouter(
    prefix="/proyectos/{project_id}/miembros", dependencies=[Depends(exige_lector)]
)


@router.get("", response_class=HTMLResponse)
def panel(
    project_id: int,
    request: Request,
    aviso: str = "",
    acceso: Acceso = Depends(exige_lector),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Cualquier miembro ve quién participa; solo el dueño ve los controles."""
    actuales = miembros_service.listar(session, project_id)
    ya_estan = {u.id for _, u in actuales}
    return templates.TemplateResponse(request, "miembros/panel.html", {
        "proyecto": acceso.proyecto,
        "acceso": acceso,
        "miembros": actuales,
        "candidatos": [
            u for u in usuarios_service.listar(session) if u.id not in ya_estan and u.activo
        ],
        "roles": ETIQUETA_ROL,
        "descripcion_rol": DESCRIPCION_ROL,
        "aviso": aviso.strip()[:500] or None,
    })


@router.post("", dependencies=[Depends(exige_duenio)])
def agregar(
    project_id: int,
    usuario_id: str = Form(...),
    rol: str = Form(Rol.editor.value),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if not usuario_id.strip().isdigit():
        return _volver(project_id, "Elegí a quién sumar")
    try:
        miembros_service.agregar(session, project_id, int(usuario_id), _rol(rol))
    except MiembroInvalido as error:
        return _volver(project_id, str(error))
    return _volver(project_id, "Miembro agregado")


@router.post("/{usuario_id}/rol", dependencies=[Depends(exige_duenio)])
def cambiar_rol(
    project_id: int,
    usuario_id: int,
    rol: str = Form(...),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    try:
        miembros_service.cambiar_rol(session, project_id, usuario_id, _rol(rol))
    except MiembroInvalido as error:
        return _volver(project_id, str(error))
    return _volver(project_id, "Rol actualizado")


@router.post("/{usuario_id}/quitar", dependencies=[Depends(exige_duenio)])
def quitar(
    project_id: int,
    usuario_id: int,
    session: Session = Depends(get_session),
) -> RedirectResponse:
    try:
        miembros_service.quitar(session, project_id, usuario_id)
    except MiembroInvalido as error:
        return _volver(project_id, str(error))
    return _volver(project_id, "Miembro quitado del proyecto")


def _rol(crudo: str) -> Rol:
    """Enum cerrado: lo que no esté en la lista cae en el rol más limitado."""
    try:
        return Rol(crudo.strip())
    except ValueError:
        return Rol.lector


def _volver(project_id: int, aviso: str) -> RedirectResponse:
    destino = f"/proyectos/{project_id}/miembros"
    if aviso:
        destino += "?" + urlencode({"aviso": aviso})
    return RedirectResponse(destino, status_code=303)
