"""Contratos del motor de scheduling.

El motor no conoce FastAPI ni SQLModel: entra y sale por estas dataclasses planas.
Cualquier capa de arriba traduce sus modelos a estos tipos antes de calcular.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


@dataclass(frozen=True)
class TaskNode:
    """Una tarea tal como la ve el motor. `duracion` se ignora si tiene hijas.

    Duración 0 = hito: marca un momento, no consume tiempo del cronograma.
    """

    id: int
    titulo: str
    parent_id: int | None = None
    duracion: int = 1
    snet: date | None = None
    orden: int = 0

    @property
    def es_hito(self) -> bool:
        return self.duracion == 0


class TipoDependencia(str, Enum):
    """Qué extremo de cada tarea se vincula.

    FS es lo normal (una empieza cuando termina la otra). SS existe para el trabajo
    que corre *en paralelo* a otro —supervisar mientras se ejecuta, por ejemplo—, que
    sin este tipo hay que declararlo mal como FS y empuja el cronograma. FF es para lo
    que tiene que terminar junto con otra cosa.
    """

    FS = "FS"  # Fin → Inicio: arranca cuando termina la predecesora
    SS = "SS"  # Inicio → Inicio: arrancan juntas
    FF = "FF"  # Fin → Fin: terminan juntas

    @property
    def etiqueta(self) -> str:
        return {
            TipoDependencia.FS: "cuando termina",
            TipoDependencia.SS: "cuando arranca",
            TipoDependencia.FF: "para terminar con",
        }[self]


@dataclass(frozen=True)
class DependencyEdge:
    """Dependencia con lag en días hábiles (negativo = adelanta)."""

    predecessor_id: int
    successor_id: int
    lag: int = 0
    tipo: TipoDependencia = TipoDependencia.FS


@dataclass
class ScheduledTask:
    """Resultado del cálculo para una tarea."""

    id: int
    inicio: date
    fin: date
    es_resumen: bool = False
    es_hito: bool = False
    holgura: int = 0
    critica: bool = False


@dataclass
class Schedule:
    """Cronograma completo de un proyecto."""

    tareas: dict[int, ScheduledTask] = field(default_factory=dict)
    inicio: date | None = None
    fin: date | None = None

    def get(self, task_id: int) -> ScheduledTask | None:
        return self.tareas.get(task_id)


class ScheduleError(Exception):
    """Base de los errores del motor. Siempre lleva un mensaje mostrable al usuario."""


class CycleError(ScheduleError):
    """El grafo de dependencias tiene un ciclo."""

    def __init__(self, ciclo: list[int]) -> None:
        self.ciclo = ciclo
        cadena = " → ".join(str(t) for t in ciclo)
        super().__init__(f"Las dependencias forman un ciclo: {cadena}")


class DanglingReferenceError(ScheduleError):
    """Una dependencia apunta a una tarea que no existe."""

    def __init__(self, task_id: int) -> None:
        self.task_id = task_id
        super().__init__(f"Hay una dependencia que apunta a una tarea inexistente ({task_id})")


class SummaryDependencyError(ScheduleError):
    """Una dependencia toca una tarea resumen; solo se permiten entre hojas."""

    def __init__(self, task_id: int) -> None:
        self.task_id = task_id
        super().__init__(
            f"La tarea {task_id} tiene subtareas: las dependencias solo se permiten "
            "entre tareas sin subtareas"
        )


class TreeError(ScheduleError):
    """El árbol de tareas es inválido (padre inexistente o ciclo de jerarquía)."""
