"""Descarga del proyecto en JSON y Markdown."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlmodel import Session

from ..db import get_session
from ..services import export as export_service
from ..services import projects as projects_service
from ..templating import templates

router = APIRouter(prefix="/proyectos/{project_id}/export")


@router.get("/json")
def json_(
    project_id: int, request: Request, session: Session = Depends(get_session)
) -> Response:
    datos = export_service.a_json(session, project_id)
    if datos is None:
        return _no_existe(request)
    cuerpo = json.dumps(datos, ensure_ascii=False, indent=2)
    return _descarga(session, project_id, cuerpo, "application/json", "json")


@router.get("/markdown")
def markdown(
    project_id: int, request: Request, session: Session = Depends(get_session)
) -> Response:
    cuerpo = export_service.a_markdown(session, project_id)
    if cuerpo is None:
        return _no_existe(request)
    return _descarga(session, project_id, cuerpo, "text/markdown; charset=utf-8", "md")


def _descarga(
    session: Session, project_id: int, cuerpo: str, tipo: str, extension: str
) -> Response:
    proyecto = projects_service.obtener(session, project_id)
    archivo = export_service.nombre_de_archivo(proyecto, extension)
    return Response(
        content=cuerpo,
        media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{archivo}"'},
    )


def _no_existe(request: Request) -> Response:
    return templates.TemplateResponse(
        request, "error.html", {"mensaje": "Ese proyecto no existe"}, status_code=404
    )
