"""Carga masiva dentro de un proyecto abierto: planilla y texto pegado.

Vive aparte de `tasks.py` porque es otra responsabilidad —traer muchas tareas de
afuera, con sus límites de tamaño— y porque ese archivo estaba llegando al techo.
Los límites de acá son control de seguridad, no comodidad: un archivo o un pegado
sin tope es la forma más barata de tumbar el proceso.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from ..db import get_session
from ..services import importar_aplicar
from ..services import importar_excel
from ..services import importar_texto
from ._tablero import render

router = APIRouter(prefix="/proyectos/{project_id}")

_MAXIMO_PLANILLA = 5 * 1024 * 1024
_MAXIMO_PEGADO = 200_000


@router.post("/importar", response_class=HTMLResponse)
async def importar_planilla(
    project_id: int,
    request: Request,
    archivo: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Suma las tareas de una planilla al proyecto abierto."""
    if not (archivo.filename or "").lower().endswith((".xlsx", ".xlsm")):
        return render(request, session, project_id, aviso="Tiene que ser un .xlsx o .xlsm")

    contenido = await archivo.read()
    if len(contenido) > _MAXIMO_PLANILLA:
        return render(request, session, project_id, aviso="La planilla supera los 5 MB")

    try:
        importacion = importar_excel.leer(contenido)
    except Exception:  # openpyxl levanta de todo con archivos corruptos
        return render(
            request, session, project_id,
            aviso="No pude leer la planilla: ¿está corrupta o protegida?",
        )
    if not importacion.filas:
        return render(
            request, session, project_id,
            aviso="No encontré tareas: la planilla necesita columnas «WBS» y «Tarea»",
        )

    avisos = importar_aplicar.agregar_a_proyecto(session, project_id, importacion)
    return render(request, session, project_id, aviso="; ".join(avisos) or None)


@router.post("/pegar", response_class=HTMLResponse)
def pegar(
    project_id: int,
    request: Request,
    texto: str = Form(""),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    if len(texto) > _MAXIMO_PEGADO:
        return render(request, session, project_id, aviso="El texto pegado es demasiado grande")
    importacion = importar_texto.leer(texto)
    if not importacion.filas:
        return render(request, session, project_id, aviso="No encontré tareas en lo que pegaste")
    avisos = importar_aplicar.agregar_a_proyecto(session, project_id, importacion)
    return render(request, session, project_id, aviso="; ".join(avisos) or None)
