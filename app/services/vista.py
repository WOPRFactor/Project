"""Arma lo que la plantilla necesita: filas del árbol con fechas y barras del timeline.

Junta árbol + cronograma + grilla en una sola estructura para que el Jinja quede
tonto: iterar y pintar, sin calcular nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlmodel import Session

from ..engine.timeline import Grilla, ancho_columna, barra, construir_grilla
from ..models import Dependency, Task
from . import dependencies as dependencies_service
from . import schedule as schedule_service
from . import tasks as tasks_service


@dataclass
class Fila:
    tarea: Task
    nivel: int
    es_resumen: bool
    es_hito: bool = False
    inicio: date | None = None
    fin: date | None = None
    holgura: int = 0
    critica: bool = False
    columnas: tuple[int, int] | None = None
    predecesoras: list[Dependency] | None = None


@dataclass
class VistaProyecto:
    filas: list[Fila]
    grilla: Grilla | None
    columna_hoy: int | None
    error: str | None
    ancho_dia: int = 22


def armar(session: Session, project_id: int, hoy: date | None = None) -> VistaProyecto:
    cronograma, error = schedule_service.calcular_seguro(session, project_id)
    nodos = tasks_service.arbol(session, project_id)
    entrantes = dependencies_service.por_sucesora(session, project_id)

    grilla = None
    if cronograma.inicio is not None and cronograma.fin is not None:
        grilla = construir_grilla(cronograma.inicio, cronograma.fin)

    filas: list[Fila] = []
    for tarea, nivel in nodos:
        calculada = cronograma.get(tarea.id or 0)
        fila = Fila(
            tarea=tarea,
            nivel=nivel,
            es_resumen=bool(calculada and calculada.es_resumen),
            es_hito=tarea.duracion == 0,
            predecesoras=entrantes.get(tarea.id or 0, []),
        )
        if calculada is not None:
            fila.inicio = calculada.inicio
            fila.fin = calculada.fin
            fila.holgura = calculada.holgura
            fila.critica = calculada.critica
            if grilla is not None:
                fila.columnas = barra(grilla, calculada.inicio, calculada.fin)
        filas.append(fila)

    return VistaProyecto(
        filas=filas,
        grilla=grilla,
        columna_hoy=grilla.columna_de(hoy or date.today()) if grilla else None,
        error=error,
        ancho_dia=ancho_columna(grilla.columnas) if grilla else 22,
    )
