"""Armado de los documentos descargables (Fase 30): puente entre services y plantillas.

Vive en `routers/` y no en `services/` porque **renderiza Jinja**, y un service de este
repo no importa templates. Lo comparten la pantalla del informe y las cuatro descargas,
así el diccionario de etiquetas no se escribe dos veces y no se desincroniza.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Session

from ..models import ETIQUETA_ESTADO_RIESGO
from ..services import documento as documento_service
from ..services import informe as informe_service
from ..services import matriz as matriz_service
from ..templating import templates

# Los mapas de etiquetas que la plantilla del informe necesita para no traducir enums
# a mano. Son constantes: se arman una vez.
ETIQUETAS_DE_RIESGO = {
    "estados_riesgo": ETIQUETA_ESTADO_RIESGO,
    "etiqueta_zona": matriz_service.ETIQUETA_ZONA,
    "etiqueta_probabilidad": matriz_service.ETIQUETA_PROBABILIDAD,
    "etiqueta_impacto": matriz_service.ETIQUETA_IMPACTO,
}


def plan(session: Session, project_id: int, hoy: date | None = None):
    return documento_service.armar(session, project_id, hoy)


def informe(session: Session, project_id: int, corte: date | None = None):
    return informe_service.armar(session, project_id, corte)


def html_del_plan(plan_armado) -> str:
    """El plan como documento autocontenido, listo para imprimir."""
    return templates.get_template("documentos/plan.html").render(plan=plan_armado)


def html_del_informe(informe_armado) -> str:
    """El informe como documento autocontenido. El Gantt se comprime al ancho de la
    hoja vertical: sin esto Chrome le corta los últimos meses sin avisar."""
    documento_service.ajustar_al_papel(informe_armado, horizontal=False)
    return templates.get_template("documentos/informe.html").render(
        informe=informe_armado, **ETIQUETAS_DE_RIESGO
    )
