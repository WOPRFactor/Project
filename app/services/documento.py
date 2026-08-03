"""Arma el **plan de trabajo** como documento: datos, no HTML.

Es el hermano de `informe.py` y contesta otra pregunta. El informe dice *cómo venimos*
a una fecha de corte y se apoya en la línea base; el plan dice *qué hay que hacer* —
todas las tareas, sus fechas y su Gantt. Por eso el plan **no** exige línea base ni
pesos cerrados: se emite igual y avisa lo que falte, porque negarle a alguien el plan
de obra porque los pesos no suman 100 sería absurdo.

Sale **completo siempre**: todas las tareas, sin importar qué etapas dejaste plegadas
ni qué columnas apagaste en la pantalla. Un documento que cambia según cómo quedó tu
sesión es una trampa cuando lo mandás por mail.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session

from ..models import Project
from ..models_base import LineaBase
from . import gantt_vista
from . import linea_base as linea_base_service
from . import projects as projects_service
from . import vista as vista_service
from .resumen import Resumen

# Ancho útil del timeline en el papel, ya descontados los márgenes y lo que se lleva el
# panel izquierdo al imprimir (340px en el plan, 300px en el informe; ver documento.css y
# el `@media print` de estilo.css). A4 a 96dpi: horizontal 297mm ≈ 1047px, vertical
# 210mm ≈ 688px.
ANCHO_TIMELINE_HORIZONTAL = 700
ANCHO_TIMELINE_VERTICAL = 430

# Nunca más ancho que lo que usa la pantalla: un proyecto de dos semanas no tiene por
# qué estirarse hasta ocupar toda la hoja.
ANCHO_DIA_MAXIMO = 22

# Por debajo de este ancho por día, los rótulos de las barras y las etiquetas de semana
# se pisan y no se leen: el documento pasa a modo comprimido y deja solo los meses.
ANCHO_COMPRIMIDO = 8


class DocumentoInvalido(Exception):
    """No se puede emitir; el mensaje se le muestra al usuario."""


@dataclass
class Plan:
    """Lo que necesita la plantilla del plan. Los nombres `filas`, `grilla`,
    `ancho_dia`, `columna_hoy` y `hay_base` son el contrato que comparte con
    `Informe`, porque los dos alimentan `partials/gantt_documento.html`."""

    proyecto: Project
    hoy: date
    resumen: Resumen = field(default_factory=Resumen)
    por_ambito: list = field(default_factory=list)
    avance: int = 0
    proximo_hito: object | None = None
    linea_base: LineaBase | None = None
    filas: list = field(default_factory=list)
    titulo_panel: str = "Tarea"
    grilla: object | None = None
    ancho_dia: float = ANCHO_DIA_MAXIMO
    columna_hoy: int | None = None
    comprimido: bool = False
    # Lo que falta para que el documento se lea sin sorpresas (pesos abiertos, por
    # ejemplo). Se avisa dentro del documento; no impide emitirlo.
    avisos: list[str] = field(default_factory=list)

    @property
    def hay_base(self) -> bool:
        return self.linea_base is not None


def armar(session: Session, project_id: int, hoy: date | None = None) -> Plan:
    proyecto = projects_service.obtener(session, project_id)
    if proyecto is None:
        raise DocumentoInvalido("Ese proyecto no existe")

    hoy = hoy or date.today()
    base = linea_base_service.fechas_base(session, project_id)
    datos = vista_service.armar(
        session, project_id, hoy=hoy,
        mirada=gantt_vista.Mirada(detalle=gantt_vista.TODO), base=base,
    )
    if datos.error:
        raise DocumentoInvalido(f"El cronograma no se puede calcular: {datos.error}")
    if not datos.todas_las_filas:
        raise DocumentoInvalido("El proyecto no tiene tareas")

    avisos = [n.mensaje for n in datos.niveles_abiertos]
    if avisos:
        avisos.insert(0, "Los pesos no cierran, así que el avance es aproximado:")

    plan = Plan(
        proyecto=proyecto,
        hoy=hoy,
        resumen=datos.resumen,
        por_ambito=datos.por_ambito,
        avance=datos.avance_ponderado,
        proximo_hito=datos.proximo_hito,
        linea_base=linea_base_service.vigente(session, project_id),
        filas=datos.todas_las_filas,
        grilla=datos.grilla,
        columna_hoy=datos.columna_hoy,
        avisos=avisos,
    )
    ajustar_al_papel(plan, horizontal=True)
    return plan


def ajustar_al_papel(documento, horizontal: bool) -> None:
    """Comprime el Gantt para que entre en el ancho de la hoja.

    Sin esto, el proyecto de 321 días hábiles que la pantalla dibuja a 6px por día son
    1926px de timeline en una hoja de 1047px, y Chrome **corta** lo que sobra: el Gantt
    sale mutilado sin avisar. Comprimirlo es lo que hace cualquier Gantt impreso; perder
    los últimos ocho meses, no.

    Sirve tanto para el `Plan` como para el `Informe`: los dos exponen `grilla`,
    `ancho_dia` y `comprimido`, que es el contrato de `partials/gantt_documento.html`.
    """
    disponible = ANCHO_TIMELINE_HORIZONTAL if horizontal else ANCHO_TIMELINE_VERTICAL
    columnas = documento.grilla.columnas if documento.grilla else 0
    documento.ancho_dia = ancho_de_dia(columnas, disponible)
    documento.comprimido = documento.ancho_dia < ANCHO_COMPRIMIDO


def ancho_de_dia(columnas: int, disponible: int) -> float:
    """Píxeles por día hábil para que `columnas` días entren en `disponible` píxeles.

    Devuelve **fracciones** y no un entero redondeado hacia abajo: con 415 días en 700px,
    truncar a 1px desperdiciaba el 40% del ancho de la hoja y dejaba los meses tan
    angostos que las etiquetas se pisaban. 1.68px por día usa la hoja entera.

    Los centésimos se truncan, **nunca se redondean**: 700/415 redondeado a 1.69 da 701px
    de timeline y Chrome corta el último día. Dos decimales para abajo entran siempre.

    Piso de 1px: es fea pero honesta —muestra el proyecto completo— y una barra de dos
    semanas todavía mide 10px. Los hitos, que ocupan un día solo, los rescata el
    `min-width` de `documento.css`.
    """
    if columnas <= 0:
        return float(ANCHO_DIA_MAXIMO)
    justo = math.floor(disponible / columnas * 100) / 100
    return max(1.0, min(float(ANCHO_DIA_MAXIMO), justo))
