"""Las personas del proyecto y qué tiene asignado cada una. HTTP puro: las
cuentas de carga viven en `services/equipo.py`."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from ..auth.dependencias import exige_usuario
from ..db import get_session
from ..services import contactos as contactos_service
from ..services import equipo as equipo_service
from ..services import linea_base as linea_base_service
from ..services import projects as projects_service
from ..services import vista as vista_service
from ..services.contactos import ContactoInvalido
from ..templating import templates

router = APIRouter(prefix="/proyectos/{project_id}/equipo", dependencies=[Depends(exige_usuario)])


@router.get("", response_class=HTMLResponse)
def panel(
    project_id: int, request: Request, aviso: str = "", session: Session = Depends(get_session)
) -> HTMLResponse:
    proyecto = projects_service.obtener(session, project_id)
    if proyecto is None:
        return templates.TemplateResponse(
            request, "error.html", {"mensaje": "Ese proyecto no existe"}, status_code=404
        )

    base = linea_base_service.fechas_base(session, project_id)
    datos = vista_service.armar(session, project_id, base=base)
    return templates.TemplateResponse(request, "equipo/lista.html", {
        "proyecto": proyecto,
        "contactos": contactos_service.listar(session, project_id),
        "cargas": equipo_service.cargas(session, project_id, datos),
        "etapas_sin_responsable": [
            f for f in datos.todas_las_filas if f.es_resumen and f.responsable is None
        ],
        "aviso": aviso or None,
    })


@router.post("")
def crear(
    project_id: int,
    nombre: str = Form(...),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if contactos_service.resolver(session, project_id, nombre) is None:
        return _volver(project_id, "El nombre no puede quedar vacío")
    return _volver(project_id, "")


@router.post("/{contacto_id}")
def renombrar(
    project_id: int,
    contacto_id: int,
    nombre: str = Form(...),
    mail: str = Form(""),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if not _del_proyecto(session, project_id, contacto_id):
        return _volver(project_id, "Esa persona no es de este proyecto")
    try:
        contactos_service.renombrar(session, contacto_id, nombre, mail)
    except ContactoInvalido as error:
        return _volver(project_id, str(error))
    return _volver(project_id, "")


@router.post("/{contacto_id}/unir")
def unir(
    project_id: int,
    contacto_id: int,
    destino_id: str = Form(""),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    if not _del_proyecto(session, project_id, contacto_id):
        return _volver(project_id, "Esa persona no es de este proyecto")
    if not destino_id.strip().isdigit():
        return _volver(project_id, "Elegí con quién unirla")
    try:
        movidas = contactos_service.unir(session, contacto_id, int(destino_id))
    except ContactoInvalido as error:
        return _volver(project_id, str(error))
    return _volver(project_id, f"Unidas: {movidas} tareas cambiaron de responsable")


@router.post("/{contacto_id}/eliminar")
def eliminar(
    project_id: int, contacto_id: int, session: Session = Depends(get_session)
) -> RedirectResponse:
    if not _del_proyecto(session, project_id, contacto_id):
        return _volver(project_id, "Esa persona no es de este proyecto")
    contactos_service.eliminar(session, contacto_id)
    return _volver(project_id, "Persona borrada; sus tareas quedaron sin asignar")


def _del_proyecto(session: Session, project_id: int, contacto_id: int) -> bool:
    contacto = contactos_service.obtener(session, contacto_id)
    return contacto is not None and contacto.project_id == project_id


def _volver(project_id: int, aviso: str) -> RedirectResponse:
    destino = f"/proyectos/{project_id}/equipo"
    if aviso:
        destino += "?" + urlencode({"aviso": aviso})
    return RedirectResponse(destino, status_code=303)
