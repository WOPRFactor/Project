"""Toda plantilla tiene que parsear.

Un `{% if %}` sin cerrar no se nota hasta que alguien abre esa pantalla, y varias
solo se ven con cierto rol o cierto estado del proyecto. Esto las revisa todas de
una, en un test que corre siempre.
"""

from pathlib import Path

import pytest

from app.templating import templates

DIRECTORIO = Path(__file__).resolve().parents[1] / "app" / "templates"
PLANTILLAS = sorted(p.relative_to(DIRECTORIO).as_posix() for p in DIRECTORIO.rglob("*.html"))


def test_hay_plantillas_para_revisar():
    assert len(PLANTILLAS) > 15


@pytest.mark.parametrize("nombre", PLANTILLAS)
def test_la_plantilla_parsea(nombre):
    templates.env.get_template(nombre)
