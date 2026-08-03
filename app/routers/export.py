"""Descarga del proyecto: JSON, Markdown, Excel y —desde la Fase 30— PDF y Word.

Dos documentos con dos formatos cada uno. El **plan** dice qué hay que hacer; el
**informe** dice cómo venimos a una fecha de corte. El PDF sale igual que la pantalla
(lo imprime el Chrome del sistema) y el Word es para retocar antes de mandarlo.
"""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlmodel import Session

from ..auth.dependencias import Acceso, exige_editor, exige_lector
from ..db import get_session
from ..services import export as export_service
from ..services import exportar_docx, exportar_excel, exportar_pdf
from ..services import projects as projects_service
from ..services.documento import DocumentoInvalido
from ..services.exportar_pdf import PdfNoDisponible
from ..services.informe import InformeInvalido
from ..templating import templates
from . import _documentos

router = APIRouter(prefix="/proyectos/{project_id}/export", dependencies=[Depends(exige_lector)])

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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


@router.get("/excel")
def excel(
    project_id: int, request: Request, session: Session = Depends(get_session)
) -> Response:
    """La grilla completa. Reimportar este archivo reproduce el proyecto."""
    cuerpo = exportar_excel.a_excel(session, project_id)
    if cuerpo is None:
        return _no_existe(request)
    return _descarga(
        session, project_id, cuerpo,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx",
    )


@router.get("/plan.pdf")
def plan_pdf(
    project_id: int, request: Request, session: Session = Depends(get_session)
) -> Response:
    """El plan completo, tal como se ve en pantalla. Hoja horizontal."""
    return _documento(
        request, session, project_id, "plan", PDF, "pdf",
        lambda: exportar_pdf.desde_html(
            _documentos.html_del_plan(_documentos.plan(session, project_id)),
            horizontal=True,
        ),
    )


@router.get("/plan.docx")
def plan_docx(
    project_id: int, request: Request, session: Session = Depends(get_session)
) -> Response:
    """El plan en Word, para retocarlo. Sin Gantt: ver `exportar_docx`."""
    return _documento(
        request, session, project_id, "plan", DOCX, "docx",
        lambda: exportar_docx.del_plan(_documentos.plan(session, project_id)),
    )


@router.get("/informe.pdf")
def informe_pdf(
    project_id: int,
    request: Request,
    corte: str = "",
    session: Session = Depends(get_session),
) -> Response:
    return _documento(
        request, session, project_id, "informe", PDF, "pdf",
        lambda: exportar_pdf.desde_html(
            _documentos.html_del_informe(
                _documentos.informe(session, project_id, _corte(corte))
            )
        ),
    )


@router.get("/informe.docx")
def informe_docx(
    project_id: int,
    request: Request,
    corte: str = "",
    session: Session = Depends(get_session),
) -> Response:
    return _documento(
        request, session, project_id, "informe", DOCX, "docx",
        lambda: exportar_docx.del_informe(
            _documentos.informe(session, project_id, _corte(corte))
        ),
    )


def _documento(
    request: Request,
    session: Session,
    project_id: int,
    clase: str,
    tipo: str,
    extension: str,
    armar,
) -> Response:
    """Las cuatro descargas comparten el manejo de errores: un proyecto sin tareas, un
    informe que no se puede emitir o un Chrome que falta se contestan con un mensaje
    claro, nunca con un stack trace ni un archivo roto."""
    try:
        cuerpo = armar()
    except (DocumentoInvalido, InformeInvalido, PdfNoDisponible) as error:
        return templates.TemplateResponse(
            request, "error.html", {"mensaje": str(error)}, status_code=400
        )
    proyecto = projects_service.obtener(session, project_id)
    archivo = f"{clase}-{export_service.nombre_de_archivo(proyecto, extension)}"
    return Response(
        content=cuerpo,
        media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{archivo}"'},
    )


def _corte(crudo: str) -> date | None:
    """Un corte inválido no rompe la descarga: se emite a hoy, como en la pantalla."""
    try:
        return date.fromisoformat(crudo.strip()) if crudo.strip() else None
    except ValueError:
        return None


def _descarga(
    session: Session, project_id: int, cuerpo: str | bytes, tipo: str, extension: str
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
