"""Rutas de proyectos."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from ..auth.dependencias import exige_usuario
from ..db import get_session
from ..models import EstadoProyecto
from ..schemas import ProyectoIn
from ..services import projects as projects_service
from ..templating import templates
from ._tablero import Mirada, contexto, mirada_query

router = APIRouter(dependencies=[Depends(exige_usuario)])


@router.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    archivados: bool = False,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    proyectos = projects_service.listar(session, incluir_archivados=archivados)
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
    session: Session = Depends(get_session),
) -> RedirectResponse:
    datos = ProyectoIn(
        nombre=nombre, descripcion=descripcion, fecha_inicio=fecha_inicio, estado=estado
    )
    proyecto = projects_service.crear(session, datos)
    return RedirectResponse(f"/proyectos/{proyecto.id}", status_code=303)


@router.get("/proyectos/{project_id}", response_class=HTMLResponse)
def detalle(
    project_id: int,
    request: Request,
    aviso: str = "",
    mirada: Mirada = Depends(mirada_query),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    # Sin parámetros de vista en la URL (venir de la home, de Equipo…), se retoma
    # la última mirada guardada; con parámetros, manda la URL y quedará guardada.
    de_mirada = ("detalle", "etapa", "color", "columnas", "colapsadas", "flechas")
    if not any(k in request.query_params for k in de_mirada):
        mirada = projects_service.vista_guardada(session, project_id)

    datos = contexto(session, project_id, mirada)
    if datos["proyecto"] is None:
        return templates.TemplateResponse(
            request, "error.html", {"mensaje": "Ese proyecto no existe"}, status_code=404
        )
    # El import de proyecto nuevo redirige acá con sus avisos en la URL.
    datos["aviso"] = aviso.strip()[:1500] or None
    return templates.TemplateResponse(request, "proyectos/detalle.html", datos)


@router.get("/proyectos/{project_id}/editar", response_class=HTMLResponse)
def editar(
    project_id: int, request: Request, session: Session = Depends(get_session)
) -> HTMLResponse:
    proyecto = projects_service.obtener(session, project_id)
    if proyecto is None:
        return templates.TemplateResponse(
            request, "error.html", {"mensaje": "Ese proyecto no existe"}, status_code=404
        )
    return templates.TemplateResponse(
        request, "proyectos/form.html", {"proyecto": proyecto, "hoy": date.today()}
    )


@router.post("/proyectos/{project_id}/editar")
def actualizar(
    project_id: int,
    nombre: str = Form(...),
    descripcion: str = Form(""),
    fecha_inicio: date = Form(...),
    estado: EstadoProyecto = Form(EstadoProyecto.activo),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    datos = ProyectoIn(
        nombre=nombre, descripcion=descripcion, fecha_inicio=fecha_inicio, estado=estado
    )
    projects_service.actualizar(session, project_id, datos)
    return RedirectResponse(f"/proyectos/{project_id}", status_code=303)


@router.post("/proyectos/{project_id}/eliminar")
def eliminar(project_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    projects_service.eliminar(session, project_id)
    return RedirectResponse("/", status_code=303)
