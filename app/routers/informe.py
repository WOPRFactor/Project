"""El informe de estado. HTTP puro: parsear el corte, llamar al service, renderizar."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from ..db import get_session
from ..models import ETIQUETA_ESTADO_RIESGO
from ..services import informe as informe_service
from ..services import matriz as matriz_service
from ..services.informe import InformeInvalido
from ..templating import templates

router = APIRouter(prefix="/proyectos/{project_id}")


@router.get("/informe", response_class=HTMLResponse)
def informe(
    project_id: int,
    request: Request,
    corte: str = "",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    try:
        datos = informe_service.armar(session, project_id, _fecha(corte))
    except InformeInvalido as error:
        return templates.TemplateResponse(
            request, "error.html", {"mensaje": str(error)}, status_code=400
        )
    return templates.TemplateResponse(request, "informe/hoja.html", {
        "informe": datos,
        "estados_riesgo": ETIQUETA_ESTADO_RIESGO,
        "etiqueta_zona": matriz_service.ETIQUETA_ZONA,
        "etiqueta_probabilidad": matriz_service.ETIQUETA_PROBABILIDAD,
        "etiqueta_impacto": matriz_service.ETIQUETA_IMPACTO,
    })


def _fecha(crudo: str) -> date | None:
    """Un corte inválido no rompe nada: se informa a hoy."""
    try:
        return date.fromisoformat(crudo.strip()) if crudo.strip() else None
    except ValueError:
        return None
