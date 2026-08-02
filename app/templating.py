"""Configuración de Jinja2. Autoescape activo (default de Jinja2Templates)."""

from __future__ import annotations

from datetime import date

from fastapi.templating import Jinja2Templates

from .config import RAIZ
from .models import ETIQUETA_AMBITO, ETIQUETA_COLOR, ETIQUETA_ESTADO_PROYECTO
from .services.gantt_vista import avance, clase_color

templates = Jinja2Templates(directory=RAIZ / "app" / "templates")


def formato_fecha(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "—"


templates.env.filters["fecha"] = formato_fecha
templates.env.globals["etiqueta_estado_proyecto"] = ETIQUETA_ESTADO_PROYECTO
templates.env.globals["etiqueta_color"] = ETIQUETA_COLOR
# Decisiones de presentación del Gantt: función pura, testeada aparte.
templates.env.globals["clase_color"] = clase_color
templates.env.globals["avance_de"] = avance
templates.env.globals["etiqueta_ambito"] = ETIQUETA_AMBITO


def etiqueta_ambito_texto(valor: str) -> str:
    """El ámbito congelado en una línea base se guarda como texto, no como enum."""
    return next((e for a, e in ETIQUETA_AMBITO.items() if a.value == valor), valor)


templates.env.globals["etiqueta_ambito_texto"] = etiqueta_ambito_texto


def _contexto_de_sesion(request):
    """`usuario` y `csrf_token` disponibles en toda plantilla, sin pasarlos a mano."""
    return {
        "usuario": getattr(request.state, "usuario", None),
        "csrf_token": getattr(request.state, "csrf_token", ""),
    }


templates.context_processors.append(_contexto_de_sesion)
