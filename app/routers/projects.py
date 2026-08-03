"""Rutas de proyectos.

Desde la Fase 11 **ninguna ruta parte de un `project_id` crudo**: la dependencia
`exige_lector/editor/dueño` resuelve la entidad y el permiso en un solo paso y
devuelve un `Acceso`. Si lo tenés en la mano, el chequeo ya pasó.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from ..auth.dependencias import Acceso, exige_duenio, exige_lector, exige_usuario
from ..db import get_session
from ..models import EstadoProyecto
from ..models_auth import Rol, Usuario
from ..schemas import ProyectoIn
from ..services import miembros as miembros_service
from ..services import projects as projects_service
from ..templating import templates
from ._tablero import Mirada, contexto, mirada_query

router = APIRouter(dependencies=[Depends(exige_usuario)])


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    archivados: bool = False,
    usuario: Usuario = Depends(exige_usuario),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Solo tus proyectos: el listado se filtra por membresía, no por la UI."""
    visibles = set(miembros_service.proyectos_de(session, usuario))
    proyectos = [
        p
        for p in projects_service.listar(session, incluir_archivados=archivados)
        if p.id in visibles
    ]
    return templates.TemplateResponse(
        request,
        "proyectos/lista.html",
        {"proyectos": proyectos, "archivados": archivados, "hoy": date.today()},
    )


@router.get("/proyectos/nuevo", response_class=HTMLResponse)
def nuevo(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "proyectos/form.html", {"proyecto": None, "hoy": date.today()}
    )


@router.post("/proyectos")
def crear(
    nombre: str = Form(...),
    descripcion: str = Form(""),
    fecha_inicio: date = Form(...),
    estado: EstadoProyecto = Form(EstadoProyecto.activo),
    usuario: Usuario = Depends(exige_usuario),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    datos = ProyectoIn(
        nombre=nombre, descripcion=descripcion, fecha_inicio=fecha_inicio, estado=estado
    )
    proyecto = projects_service.crear(session, datos)
    # Quien lo crea es su dueño: un proyecto nunca nace huérfano.
    miembros_service.agregar(session, proyecto.id or 0, usuario.id or 0, Rol.duenio)
    return RedirectResponse(f"/proyectos/{proyecto.id}", status_code=303)


@router.get("/proyectos/{project_id}", response_class=HTMLResponse)
def detalle(
    project_id: int,
    request: Request,
    aviso: str = "",
    mirada: Mirada = Depends(mirada_query),
    acceso: Acceso = Depends(exige_lector),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    # Sin parámetros de vista en la URL (venir de la home, de Equipo…), se retoma
    # la última mirada guardada; con parámetros, manda la URL y quedará guardada.
    de_mirada = ("detalle", "etapa", "color", "columnas", "colapsadas", "flechas")
    if not any(k in request.query_params for k in de_mirada):
        mirada = projects_service.vista_guardada(session, project_id)

    datos = contexto(session, project_id, mirada, acceso=acceso)
    # El import de proyecto nuevo redirige acá con sus avisos en la URL.
    datos["aviso"] = aviso.strip()[:1500] or None
    return templates.TemplateResponse(request, "proyectos/detalle.html", datos)


@router.get("/proyectos/{project_id}/editar", response_class=HTMLResponse)
def editar(
    project_id: int,
    request: Request,
    acceso: Acceso = Depends(exige_duenio),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "proyectos/form.html", {"proyecto": acceso.proyecto, "hoy": date.today()}
    )


@router.post("/proyectos/{project_id}/editar")
def actualizar(
    project_id: int,
    nombre: str = Form(...),
    descripcion: str = Form(""),
    fecha_inicio: date = Form(...),
    estado: EstadoProyecto = Form(EstadoProyecto.activo),
    acceso: Acceso = Depends(exige_duenio),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    datos = ProyectoIn(
        nombre=nombre, descripcion=descripcion, fecha_inicio=fecha_inicio, estado=estado
    )
    projects_service.actualizar(session, project_id, datos)
    return RedirectResponse(f"/proyectos/{project_id}", status_code=303)


@router.post("/proyectos/{project_id}/eliminar")
def eliminar(
    project_id: int,
    acceso: Acceso = Depends(exige_duenio),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    projects_service.eliminar(session, project_id)
    return RedirectResponse("/", status_code=303)
