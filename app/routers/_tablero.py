"""Render compartido del tablero (grilla + timeline).

Cada mutación recalcula todo el cronograma y devuelve este parcial, así la vista
siempre refleja el estado real sin recargar la página.

La **mirada** (detalle, etapa y modo de color) viaja en cada request: el contenedor
del tablero la manda con `hx-vals`, que HTMX hereda a todos los hijos. Sin eso, cada
edición te devolvería a la vista por defecto y perderías el filtro que elegiste.
"""

from __future__ import annotations

from fastapi import Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from ..services import gantt_vista
from ..services import linea_base as linea_base_service
from ..services import projects as projects_service
from ..services import tasks as tasks_service
from ..services import vista as vista_service
from ..services.gantt_vista import Mirada
from ..templating import templates


_PRENDIDO = {"1", "true", "on"}


def _leer_flechas(crudo: list[str] | None) -> bool:
    """Un checkbox sin tildar no se envía, así que el formulario manda además un
    campo oculto en `0`. Llega como lista —`["0"]` apagado, `["0", "1"]` prendido—
    y alcanza con que alguno venga prendido. Ausente del todo = prendidas, que es
    el default de la vista y lo que ve quien entra por una URL pelada."""
    if not crudo:
        return True
    return any(valor.strip() in _PRENDIDO for valor in crudo)


def _armar(
    detalle: str, etapa: str, color: str,
    columnas: list[str] | None, flechas: list[str] | None,
) -> Mirada:
    return Mirada(
        detalle=detalle,
        etapa=int(etapa) if etapa.strip().isdigit() and etapa.strip() != "0" else None,
        color=color,
        columnas=gantt_vista.leer_columnas(columnas),
        flechas=_leer_flechas(flechas),
    ).normalizada()


def mirada_form(
    detalle: str = Form(gantt_vista.TODO),
    etapa: str = Form(""),
    color: str = Form(gantt_vista.POR_CRITICIDAD),
    columnas: list[str] | None = Form(None),
    flechas: list[str] | None = Form(None),
) -> Mirada:
    """Para las mutaciones: la mirada llega como campos del formulario."""
    return _armar(detalle, etapa, color, columnas, flechas)


def mirada_query(
    detalle: str = Query(gantt_vista.TODO),
    etapa: str = Query(""),
    color: str = Query(gantt_vista.POR_CRITICIDAD),
    columnas: list[str] | None = Query(None),
    flechas: list[str] | None = Query(None),
) -> Mirada:
    """Para la pantalla del proyecto: la mirada llega en la URL, así es compartible."""
    return _armar(detalle, etapa, color, columnas, flechas)


def contexto(session: Session, project_id: int, mirada: Mirada | None = None) -> dict:
    mirada = mirada or Mirada()
    proyecto = projects_service.obtener(session, project_id)
    base = linea_base_service.fechas_base(session, project_id)
    datos = vista_service.armar(session, project_id, mirada=mirada, base=base)
    return {
        "proyecto": proyecto,
        "linea_base": linea_base_service.vigente(session, project_id),
        "desvio_ambito": linea_base_service.desvio_por_ambito(session, project_id, datos),
        "avance_planificado": linea_base_service.avance_planificado(session, project_id),
        "filas": datos.filas,
        "todas_las_filas": datos.todas_las_filas,
        "etapas": gantt_vista.etapas(datos.todas_las_filas),
        "mirada": mirada,
        "detalles": gantt_vista.DETALLES,
        "modos_color": gantt_vista.MODOS_COLOR,
        "columnas_disponibles": gantt_vista.COLUMNAS,
        "ancho_tarea": gantt_vista.ancho_tarea(datos.filas),
        "grilla": datos.grilla,
        "columna_hoy": datos.columna_hoy,
        "estados": datos.estados,
        "contactos": datos.contactos,
        "resumen": datos.resumen,
        "por_ambito": datos.por_ambito,
        "ventana": datos.ventana,
        "estimadas": datos.estimadas,
        "avance_ponderado": datos.avance_ponderado,
        "niveles_abiertos": datos.niveles_abiertos,
        "proximo_hito": datos.proximo_hito,
        "flechas": datos.flechas,
        "alto_pista": datos.alto_pista,
        "ancho_dia": datos.ancho_dia,
        "error_motor": datos.error,
        "hojas": [f.tarea for f in datos.todas_las_filas if not f.es_resumen],
        "todas": tasks_service.arbol(session, project_id),
    }


def render(
    request: Request,
    session: Session,
    project_id: int,
    aviso: str | None = None,
    mirada: Mirada | None = None,
) -> HTMLResponse:
    datos = contexto(session, project_id, mirada)
    datos["aviso"] = aviso
    return templates.TemplateResponse(request, "partials/tablero.html", datos)


__all__ = ["Depends", "Mirada", "contexto", "mirada_form", "mirada_query", "render"]
