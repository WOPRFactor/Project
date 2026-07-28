"""Configuración de Jinja2. Autoescape activo (default de Jinja2Templates)."""

from __future__ import annotations

from datetime import date

from fastapi.templating import Jinja2Templates

from .config import RAIZ
from .models import ETIQUETA_AMBITO, ETIQUETA_COLOR, ETIQUETA_ESTADO_PROYECTO

templates = Jinja2Templates(directory=RAIZ / "app" / "templates")


def formato_fecha(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "—"


templates.env.filters["fecha"] = formato_fecha
templates.env.globals["etiqueta_estado_proyecto"] = ETIQUETA_ESTADO_PROYECTO
templates.env.globals["etiqueta_color"] = ETIQUETA_COLOR
templates.env.globals["etiqueta_ambito"] = ETIQUETA_AMBITO
