"""Puente models → engine → cronograma.

Es el único lugar donde los modelos de SQLModel se traducen a las dataclasses del
motor. El motor nunca ve una Session.
"""

from __future__ import annotations

from sqlmodel import Session, select

from ..engine import DependencyEdge, Schedule, ScheduleError, TaskNode, calcular as motor_calcular, marcar
from ..models import Dependency, Project, Task


def _nodos(tareas: list[Task]) -> list[TaskNode]:
    return [
        TaskNode(
            id=t.id or 0,
            titulo=t.titulo,
            parent_id=t.parent_id,
            duracion=t.duracion,
            snet=t.snet,
            orden=t.orden,
        )
        for t in tareas
    ]


def _aristas(dependencias: list[Dependency]) -> list[DependencyEdge]:
    return [
        DependencyEdge(
            predecessor_id=d.predecessor_id,
            successor_id=d.successor_id,
            lag=d.lag,
        )
        for d in dependencias
    ]


def calcular(
    session: Session,
    project_id: int,
    extra: list[Dependency] | None = None,
) -> Schedule:
    """Cronograma del proyecto con holguras y ruta crítica marcadas.

    `extra` permite probar dependencias candidatas antes de guardarlas.
    Lanza ScheduleError si el árbol o el grafo son inválidos.
    """
    proyecto = session.get(Project, project_id)
    if proyecto is None:
        return Schedule()

    tareas = list(session.exec(select(Task).where(Task.project_id == project_id)))
    dependencias = list(
        session.exec(select(Dependency).where(Dependency.project_id == project_id))
    )
    dependencias.extend(extra or [])

    nodos = _nodos(tareas)
    aristas = _aristas(dependencias)
    cronograma = motor_calcular(proyecto.fecha_inicio, nodos, aristas)
    return marcar(cronograma, nodos, aristas)


def calcular_seguro(session: Session, project_id: int) -> tuple[Schedule, str | None]:
    """Igual que `calcular`, pero devuelve el error como texto en vez de propagarlo.

    Las vistas usan esta versión: un grafo inválido muestra un aviso, nunca un 500.
    """
    try:
        return calcular(session, project_id), None
    except ScheduleError as error:
        return Schedule(), str(error)
