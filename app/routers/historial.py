"""Historial de cambios del proyecto (Fase 12).

Solo GET, y no por olvido: la auditoría es de solo agregar. No hay ruta que edite ni
borre un `Cambio`, porque un historial que se puede corregir no sirve para lo único
que sirve un historial. Lo escriben los services al guardar; acá solo se lee.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from ..auth.dependencias import Acceso, exige_lector
from ..db import get_session
from ..services import cambios as cambios_service
from ..services import tasks as tasks_service
from ..templating import templates

router = APIRouter(
    prefix="/proyectos/{project_id}/historial", dependencies=[Depends(exige_lector)]
)

POR_PAGINA = 50


@router.get("", response_class=HTMLResponse)
def panel(
    project_id: int,
    request: Request,
    tarea: int | None = Query(None),
    pagina: int = Query(1, ge=1),
    acceso: Acceso = Depends(exige_lector),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Todo el proyecto, o la vida de una sola tarea con `?tarea=`."""
    filas, total = cambios_service.listar(
        session, project_id, task_id=tarea, pagina=pagina, por_pagina=POR_PAGINA
    )
    # Si se filtra por una tarea que ya se borró, el título igual tiene que decir de
    # cuál se trata: sale del propio historial, que guarda la etiqueta del momento.
    elegida = tasks_service.obtener(session, tarea) if tarea else None
    nombre_tarea = None
    if tarea is not None:
        nombre_tarea = (
            cambios_service.etiqueta_de(elegida)
            if elegida is not None and elegida.project_id == project_id
            else (filas[0].etiqueta if filas else f"tarea {tarea}")
        )

    ultima = max(1, -(-total // POR_PAGINA))
    return templates.TemplateResponse(request, "historial/panel.html", {
        "proyecto": acceso.proyecto,
        "acceso": acceso,
        "cambios": filas,
        "quienes": cambios_service.nombres_de_usuarios(session, filas),
        "total": total,
        "pagina": min(pagina, ultima),
        "ultima": ultima,
        "tarea_id": tarea,
        "nombre_tarea": nombre_tarea,
    })
