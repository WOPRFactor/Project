"""Arma lo que la plantilla necesita: filas del árbol con fechas y barras del timeline.

Junta árbol + cronograma + grilla en una sola estructura para que el Jinja quede
tonto: iterar y pintar, sin calcular nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session

from ..engine.calendar import contar_habiles
from ..engine.timeline import Grilla, ancho_columna, barra, construir_grilla
from ..models import Dependency, Task
from . import dependencies as dependencies_service
from . import predecesoras as predecesoras_service
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
    # Ruta crítica según el motor (holgura cero). Distinta de `tarea.critica`,
    # que es la criticidad de negocio que marca el usuario.
    sin_holgura: bool = False
    columnas: tuple[int, int] | None = None
    predecesoras: list[Dependency] | None = None
    predecesoras_texto: str = ""
    tiene_predecesoras: bool = False


@dataclass
class Resumen:
    """Cuánto dura el proyecto según el cronograma de este momento."""

    inicio: date | None = None
    fin: date | None = None
    dias_habiles: int = 0
    dias_corridos: int = 0
    tareas: int = 0
    hitos: int = 0
    hechas: int = 0

    @property
    def semanas(self) -> int:
        return -(-self.dias_habiles // 5)  # redondeo hacia arriba

    @property
    def avance(self) -> int:
        return round(100 * self.hechas / self.tareas) if self.tareas else 0


@dataclass
class VistaProyecto:
    filas: list[Fila]
    grilla: Grilla | None
    columna_hoy: int | None
    error: str | None
    resumen: Resumen = field(default_factory=Resumen)
    ancho_dia: int = 22


def _texto_predecesoras(deps: list[Dependency], codigos: dict[int, str]) -> str:
    """Lo que se ve en la celda: `1.3, 2.1SS+2`."""
    partes = [
        predecesoras_service.escribir(
            codigos.get(d.predecessor_id) or str(d.predecessor_id), d.lag, d.tipo
        )
        for d in deps
    ]
    return ", ".join(sorted(partes))


def armar(session: Session, project_id: int, hoy: date | None = None) -> VistaProyecto:
    cronograma, error = schedule_service.calcular_seguro(session, project_id)
    nodos = tasks_service.arbol(session, project_id)
    entrantes = dependencies_service.por_sucesora(session, project_id)

    grilla = None
    if cronograma.inicio is not None and cronograma.fin is not None:
        grilla = construir_grilla(cronograma.inicio, cronograma.fin)

    codigos = {t.id: t.codigo for t, _ in nodos}
    filas: list[Fila] = []
    for tarea, nivel in nodos:
        calculada = cronograma.get(tarea.id or 0)
        propias = entrantes.get(tarea.id or 0, [])
        fila = Fila(
            tarea=tarea,
            nivel=nivel,
            es_resumen=bool(calculada and calculada.es_resumen),
            es_hito=tarea.duracion == 0,
            predecesoras=propias,
            predecesoras_texto=_texto_predecesoras(propias, codigos),
            tiene_predecesoras=bool(propias),
        )
        if calculada is not None:
            fila.inicio = calculada.inicio
            fila.fin = calculada.fin
            fila.holgura = calculada.holgura
            fila.sin_holgura = calculada.critica
            if grilla is not None:
                fila.columnas = barra(grilla, calculada.inicio, calculada.fin)
        filas.append(fila)

    return VistaProyecto(
        filas=filas,
        grilla=grilla,
        columna_hoy=grilla.columna_de(hoy or date.today()) if grilla else None,
        error=error,
        resumen=_resumir(filas, cronograma.inicio, cronograma.fin),
        ancho_dia=ancho_columna(grilla.columnas) if grilla else 22,
    )


def _resumir(filas: list[Fila], inicio: date | None, fin: date | None) -> Resumen:
    """Duración total del proyecto: se recalcula sola al agregar o quitar tareas."""
    hojas = [f for f in filas if not f.es_resumen]
    return Resumen(
        inicio=inicio,
        fin=fin,
        dias_habiles=contar_habiles(inicio, fin) if inicio and fin else 0,
        dias_corridos=(fin - inicio).days + 1 if inicio and fin else 0,
        tareas=len([f for f in hojas if not f.es_hito]),
        hitos=len([f for f in hojas if f.es_hito]),
        hechas=len([f for f in hojas if f.tarea.estado.value == "hecha"]),
    )
