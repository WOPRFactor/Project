"""Rutas de tareas. Toda mutación devuelve el tablero recalculado."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlmodel import Session

from ..db import get_session
from ..models import EstadoTarea
from ..schemas import TareaIn
from ..services import tasks as tasks_service
from ..services.tasks import TareaInvalida
from ..templating import templates
from ._tablero import render

router = APIRouter(prefix="/proyectos/{project_id}/tareas")


def _datos(
    titulo: str, notas: str, duracion: int, snet: date | None, estado: EstadoTarea,
    parent_id: int | None = None,
) -> TareaIn:
    return TareaIn(
        titulo=titulo, notas=notas, duracion=duracion, snet=snet,
        estado=estado, parent_id=parent_id,
    )


@router.post("", response_class=HTMLResponse)
def crear(
    project_id: int,
    request: Request,
    titulo: str = Form(...),
    notas: str = Form(""),
    duracion: int = Form(1),
    snet: str = Form(""),
    parent_id: str = Form(""),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        datos = _datos(
            titulo, notas, duracion,
            date.fromisoformat(snet) if snet else None,
            EstadoTarea.pendiente,
            int(parent_id) if parent_id else None,
        )
        tasks_service.crear(session, project_id, datos)
    except (ValidationError, ValueError, TareaInvalida) as error:
        return render(request, session, project_id, aviso=_mensaje(error))
    return render(request, session, project_id)


@router.get("/{task_id}/editar", response_class=HTMLResponse)
def form_editar(
    project_id: int,
    task_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    tarea = tasks_service.obtener(session, task_id)
    return templates.TemplateResponse(
        request,
        "partials/tarea_form.html",
        {
            "tarea": tarea,
            "proyecto_id": project_id,
            "candidatos": tasks_service.arbol(session, project_id),
        },
    )


@router.post("/{task_id}/editar", response_class=HTMLResponse)
def actualizar(
    project_id: int,
    task_id: int,
    request: Request,
    titulo: str = Form(...),
    notas: str = Form(""),
    duracion: int = Form(1),
    snet: str = Form(""),
    estado: EstadoTarea = Form(EstadoTarea.pendiente),
    parent_id: str = Form(""),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        datos = _datos(
            titulo, notas, duracion,
            date.fromisoformat(snet) if snet else None,
            estado,
        )
        tasks_service.actualizar(session, task_id, datos)
        tasks_service.mover(session, task_id, int(parent_id) if parent_id else None)
    except (ValidationError, ValueError, TareaInvalida) as error:
        return render(request, session, project_id, aviso=_mensaje(error))
    return render(request, session, project_id)


@router.post("/{task_id}/estado", response_class=HTMLResponse)
def cambiar_estado(
    project_id: int,
    task_id: int,
    request: Request,
    estado: EstadoTarea = Form(...),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    tasks_service.cambiar_estado(session, task_id, estado)
    return render(request, session, project_id)


@router.post("/{task_id}/eliminar", response_class=HTMLResponse)
def eliminar(
    project_id: int,
    task_id: int,
    request: Request,
    promover: bool = Form(False),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    tasks_service.eliminar(session, task_id, promover_hijas=promover)
    return render(request, session, project_id)


def _mensaje(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(e.get("msg", "dato inválido") for e in error.errors())
    return str(error) or "No se pudo completar la operación"
