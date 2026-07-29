"""Importar un proyecto desde una planilla o desde texto pegado.

Nada se crea sin previsualización: primero se muestra qué entraría y qué avisos
hay, y recién con la confirmación se escribe en la base.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlmodel import Session

from ..db import get_session
from ..services import importar as importar_service
from ..services import importar_aplicar
from ..services import importar_diagnostico as diagnostico_service
from ..services import importar_excel, importar_texto
from ..services import plantilla as plantilla_service
from ..templating import templates

router = APIRouter(prefix="/importar")

MAX_BYTES = 5 * 1024 * 1024
EXTENSIONES = (".xlsx", ".xlsm")


@router.get("", response_class=HTMLResponse)
def formulario(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "importar/form.html", {"hoy": date.today(), "importacion": None}
    )


@router.get("/plantilla")
def plantilla() -> Response:
    """Planilla modelo: define el formato esperado sin que haya que documentarlo."""
    return Response(
        content=plantilla_service.construir(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="wopr-plantilla.xlsx"'},
    )


@router.post("/planilla", response_class=HTMLResponse)
async def previsualizar_planilla(
    request: Request,
    archivo: UploadFile = File(...),
    hoja: str = Form(""),
) -> HTMLResponse:
    if not (archivo.filename or "").lower().endswith(EXTENSIONES):
        return _error(request, "El archivo tiene que ser una planilla .xlsx o .xlsm")

    contenido = await archivo.read()
    if len(contenido) > MAX_BYTES:
        return _error(request, "La planilla supera los 5 MB")

    try:
        disponibles = importar_excel.hojas(contenido)
        importacion = importar_excel.leer(contenido, hoja or None)
    except Exception:  # openpyxl levanta de todo con archivos corruptos
        return _error(request, "No pude leer la planilla: ¿está corrupta o protegida?")

    return _preview(request, importacion, hojas=disponibles, hoja_elegida=hoja)


@router.post("/texto", response_class=HTMLResponse)
def previsualizar_texto(request: Request, texto: str = Form("")) -> HTMLResponse:
    if len(texto) > 200_000:
        return _error(request, "El texto pegado es demasiado grande")
    return _preview(request, importar_texto.leer(texto))


@router.post("/confirmar", response_model=None)
def confirmar(
    request: Request,
    nombre: str = Form(...),
    fecha_inicio: date = Form(...),
    carga: str = Form(...),
    corregir: str = Form(""),
    session: Session = Depends(get_session),
) -> Response:
    importacion = importar_service.desde_json(carga)
    if importacion is None or not importacion.filas:
        return _error(request, "Se perdió la previsualización. Volvé a cargar la fuente.")

    if corregir.strip():
        diagnostico = diagnostico_service.analizar(importacion)
        diagnostico_service.aplicar_sugerencias(importacion, diagnostico)

    proyecto, avisos = importar_aplicar.aplicar(session, nombre, fecha_inicio, importacion)
    destino = f"/proyectos/{proyecto.id}"
    if avisos:
        # Los textos viajan en el redirect: un conteo («avisos=3») no le dice al
        # usuario qué dependencia no se creó ni por qué.
        destino += "?" + urlencode({"aviso": "; ".join(avisos)[:1500]})
    return RedirectResponse(destino, status_code=303)


def _preview(
    request: Request,
    importacion: importar_service.Importacion,
    hojas: list[str] | None = None,
    hoja_elegida: str = "",
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "importar/form.html",
        {
            "hoy": date.today(),
            "importacion": importacion,
            "diagnostico": diagnostico_service.analizar(importacion),
            "carga": importar_service.a_json(importacion),
            "hojas": hojas or [],
            "hoja_elegida": hoja_elegida,
            "modo": "nuevo",
            "accion": "/importar/confirmar",
        },
    )


def _error(request: Request, mensaje: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "importar/form.html",
        {"hoy": date.today(), "importacion": None, "error": mensaje},
        status_code=400,
    )
