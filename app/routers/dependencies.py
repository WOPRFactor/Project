"""Rutas de dependencias. El rechazo de ciclos llega como aviso, nunca como 500."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlmodel import Session

from ..db import get_session
from ..schemas import DependenciaIn
from ..services import dependencies as dependencies_service
from ..services.tasks import TareaInvalida
from ._tablero import render

router = APIRouter(prefix="/proyectos/{project_id}/dependencias")


@router.post("", response_class=HTMLResponse)
def crear(
    project_id: int,
    request: Request,
    predecessor_id: int = Form(...),
    successor_id: int = Form(...),
    lag: int = Form(0),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        datos = DependenciaIn(
            predecessor_id=predecessor_id, successor_id=successor_id, lag=lag
        )
        dependencies_service.crear(session, project_id, datos)
    except (ValidationError, TareaInvalida) as error:
        return render(request, session, project_id, aviso=_mensaje(error))
    return render(request, session, project_id)


@router.post("/{dependency_id}/eliminar", response_class=HTMLResponse)
def eliminar(
    project_id: int,
    dependency_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> HTMLResponse:
    dependencies_service.eliminar(session, dependency_id)
    return render(request, session, project_id)


def _mensaje(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(e.get("msg", "dato inválido") for e in error.errors())
    return str(error) or "No se pudo crear la dependencia"
