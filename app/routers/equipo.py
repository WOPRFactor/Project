"""Las personas del proyecto y qué tiene asignado cada una."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from ..db import get_session
from ..models import Contacto, EstadoRiesgo
from ..services import contactos as contactos_service
from ..services import linea_base as linea_base_service
from ..services import projects as projects_service
from ..services import riesgos as riesgos_service
from ..services import vista as vista_service
from ..services.contactos import ContactoInvalido
from ..services.resumen import esta_hecha
from ..templating import templates

router = APIRouter(prefix="/proyectos/{project_id}/equipo")


@dataclass
class Carga:
    """Cuánto tiene encima una persona. Es la pregunta que antes no se podía hacer."""

    contacto: Contacto | None
    tareas: int = 0
    hitos: int = 0
    esfuerzo: int = 0
    hechas: int = 0
    atrasadas: int = 0
    sin_margen: int = 0
    # Riesgos que esta persona tiene que responder. Están acá porque un riesgo sin
    # dueño no lo mira nadie, y la pregunta "qué tengo encima" incluye los riesgos.
    riesgos: int = 0

    @property
    def avance(self) -> int:
        return round(100 * self.hechas / self.tareas) if self.tareas else 0


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
        "cargas": _cargas(session, project_id, datos),
        "etapas_sin_responsable": [
            f for f in datos.todas_las_filas if f.es_resumen and f.responsable is None
        ],
        "aviso": aviso or None,
    })


def _cargas(session: Session, project_id: int, datos) -> list[Carga]:
    """Una fila por persona, más una para lo que quedó sin asignar."""
    por_contacto: dict[int | None, Carga] = {}
    for contacto in contactos_service.listar(session, project_id):
        por_contacto[contacto.id] = Carga(contacto=contacto)
    por_contacto.setdefault(None, Carga(contacto=None))

    for fila in datos.todas_las_filas:
        if fila.es_resumen:
            continue
        clave = fila.responsable.id if fila.responsable else None
        carga = por_contacto.setdefault(clave, Carga(contacto=fila.responsable))
        if fila.es_hito:
            carga.hitos += 1
        else:
            carga.tareas += 1
            carga.esfuerzo += fila.tarea.duracion
        if esta_hecha(fila):
            carga.hechas += 1
        if fila.desvio is not None and fila.desvio > 0:
            carga.atrasadas += 1
        if fila.sin_holgura and not esta_hecha(fila):
            carga.sin_margen += 1

    for riesgo in riesgos_service.listar(session, project_id):
        if riesgo.estado == EstadoRiesgo.cerrado:
            continue
        carga = por_contacto.setdefault(riesgo.responsable_id, Carga(contacto=None))
        carga.riesgos += 1

    cargas = list(por_contacto.values())
    # Lo sin asignar al final: es un pendiente, no una persona.
    cargas.sort(key=lambda c: (c.contacto is None, -c.esfuerzo))
    return [
        c for c in cargas
        if c.tareas or c.hitos or c.riesgos or c.contacto is not None
    ]


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
