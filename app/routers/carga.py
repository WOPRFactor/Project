"""Carga masiva dentro de un proyecto abierto: planilla y texto pegado.

Vive aparte de `tasks.py` porque es otra responsabilidad —traer muchas tareas de
afuera, con sus límites de tamaño— y porque ese archivo estaba llegando al techo.
Los límites de acá son control de seguridad, no comodidad: un archivo o un pegado
sin tope es la forma más barata de tumbar el proceso.

**La planilla pasa por previsualización, igual que al crear un proyecto nuevo.**
Antes este camino importaba en crudo y el de la home diagnosticaba: mismo botón,
mismo archivo, dos resultados distintos según por dónde entraras. El pegado de texto
sí entra derecho, y a propósito: no trae fechas, así que no hay nada que diagnosticar.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from ..db import get_session
from ..services import importar as importar_service
from ..services import importar_aplicar
from ..services import importar_diagnostico as diagnostico_service
from ..services import importar_excel
from ..services import importar_texto
from ..services import projects as projects_service
from ..templating import templates
from ._tablero import Mirada, mirada_form, render

router = APIRouter(prefix="/proyectos/{project_id}")

_MAXIMO_PLANILLA = 5 * 1024 * 1024
_MAXIMO_PEGADO = 200_000


@router.get("/tablero", response_class=HTMLResponse)
def tablero(
    project_id: int,
    request: Request,
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Vuelve a la grilla. Es el «cancelar» de la previsualización."""
    return render(request, session, project_id, mirada=mirada)


@router.post("/importar", response_class=HTMLResponse)
async def previsualizar_planilla(
    project_id: int,
    request: Request,
    archivo: UploadFile = File(...),
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Muestra qué entraría y qué contradice a qué. No escribe nada todavía."""
    if not (archivo.filename or "").lower().endswith((".xlsx", ".xlsm")):
        return render(
            request, session, project_id,
            aviso="Tiene que ser un .xlsx o .xlsm", mirada=mirada,
        )

    contenido = await archivo.read()
    if len(contenido) > _MAXIMO_PLANILLA:
        return render(
            request, session, project_id,
            aviso="La planilla supera los 5 MB", mirada=mirada,
        )

    try:
        importacion = importar_excel.leer(contenido)
    except Exception:  # openpyxl levanta de todo con archivos corruptos
        return render(
            request, session, project_id,
            aviso="No pude leer la planilla: ¿está corrupta o protegida?", mirada=mirada,
        )
    if not importacion.filas:
        return render(
            request, session, project_id,
            aviso="No encontré tareas: la planilla necesita columnas «WBS» y «Tarea»",
            mirada=mirada,
        )

    return templates.TemplateResponse(request, "importar/preview.html", {
        "proyecto": projects_service.obtener(session, project_id),
        "importacion": importacion,
        "diagnostico": diagnostico_service.analizar(importacion),
        "carga": importar_service.a_json(importacion),
        "hoy": date.today(),
        "modo": "sumar",
        "accion": f"/proyectos/{project_id}/importar/confirmar",
    })


@router.post("/importar/confirmar", response_class=HTMLResponse)
def confirmar_planilla(
    project_id: int,
    request: Request,
    carga: str = Form(...),
    corregir: str = Form(""),
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    importacion = importar_service.desde_json(carga)
    if importacion is None or not importacion.filas:
        return render(
            request, session, project_id,
            aviso="Se perdió la previsualización. Volvé a subir la planilla.",
            mirada=mirada,
        )

    if corregir.strip():
        diagnostico = diagnostico_service.analizar(importacion)
        corregidas = diagnostico_service.aplicar_sugerencias(importacion, diagnostico)
        importacion.avisos.append(f"{corregidas} dependencias corregidas")

    avisos = importar_aplicar.agregar_a_proyecto(session, project_id, importacion)
    return render(request, session, project_id, aviso="; ".join(avisos) or None, mirada=mirada)


@router.post("/pegar", response_class=HTMLResponse)
def pegar(
    project_id: int,
    request: Request,
    texto: str = Form(""),
    mirada: Mirada = Depends(mirada_form),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Sin previsualización a propósito: el texto pegado no trae fechas que puedan
    contradecir a las dependencias, así que no hay nada que diagnosticar."""
    if len(texto) > _MAXIMO_PEGADO:
        return render(
            request, session, project_id,
            aviso="El texto pegado es demasiado grande", mirada=mirada,
        )
    importacion = importar_texto.leer(texto)
    if not importacion.filas:
        return render(
            request, session, project_id,
            aviso="No encontré tareas en lo que pegaste", mirada=mirada,
        )
    avisos = importar_aplicar.agregar_a_proyecto(session, project_id, importacion)
    return render(request, session, project_id, aviso="; ".join(avisos) or None, mirada=mirada)
