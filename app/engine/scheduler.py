"""Cálculo del cronograma: forward pass sobre las hojas y rollup de los resúmenes.

Regla v1: una tarea arranca en el máximo entre el inicio del proyecto, su SNET y
(fin de cada predecesora + 1 día hábil + lag). Nada arranca antes del inicio del
proyecto, ni siquiera con lag negativo.
"""

from __future__ import annotations

from datetime import date

from . import graph
from .calendar import fin_desde_inicio, siguiente_habil, sumar_habiles
from .types import DependencyEdge, Schedule, ScheduledTask, TaskNode


def salto_tras(predecesora: TaskNode) -> int:
    """Días hábiles entre el fin de una predecesora y el arranque de su sucesora.

    Una tarea normal ocupa su último día, así que la sucesora arranca al siguiente.
    Un hito no consume tiempo: lo que dependa de él arranca el mismo día.
    """
    return 0 if predecesora.es_hito else 1


def calcular(
    inicio_proyecto: date,
    nodos: list[TaskNode],
    aristas: list[DependencyEdge],
) -> Schedule:
    """Calcula el cronograma completo. Lanza ScheduleError si el input es inválido."""
    graph.validar_arbol(nodos)
    graph.validar_dependencias(nodos, aristas)

    grupos = graph.hijas_por_padre(nodos)
    por_id = {n.id: n for n in nodos}
    hojas = [n for n in nodos if not graph.es_resumen(n, grupos)]

    schedule = Schedule()
    if not nodos:
        return schedule

    arranque = siguiente_habil(inicio_proyecto)
    _forward_pass(schedule, arranque, hojas, aristas, por_id)
    _rollup(schedule, grupos)
    _fechas_de_proyecto(schedule, arranque)
    return schedule


def _forward_pass(
    schedule: Schedule,
    arranque: date,
    hojas: list[TaskNode],
    aristas: list[DependencyEdge],
    por_id: dict[int, TaskNode],
) -> None:
    ids_hoja = [n.id for n in hojas]
    hojas_validas = set(ids_hoja)
    relevantes = [
        a
        for a in aristas
        if a.predecessor_id in hojas_validas and a.successor_id in hojas_validas
    ]
    entrantes = graph.predecesoras_por_tarea(relevantes)

    for task_id in graph.orden_topologico(ids_hoja, relevantes):
        nodo = por_id[task_id]
        inicio = arranque
        for arista in entrantes.get(task_id, []):
            fin_previo = schedule.tareas[arista.predecessor_id].fin
            salto = salto_tras(por_id[arista.predecessor_id])
            inicio = max(inicio, sumar_habiles(fin_previo, salto + arista.lag))
        if nodo.snet is not None:
            inicio = max(inicio, siguiente_habil(nodo.snet))
        inicio = siguiente_habil(max(inicio, arranque))
        schedule.tareas[task_id] = ScheduledTask(
            id=task_id,
            inicio=inicio,
            fin=fin_desde_inicio(inicio, nodo.duracion),
            es_hito=nodo.es_hito,
        )


def _rollup(schedule: Schedule, grupos: dict[int | None, list[TaskNode]]) -> None:
    """Las fechas de un resumen son la envolvente de sus hijas (post-orden)."""

    def resolver(nodo: TaskNode) -> ScheduledTask | None:
        hijas = grupos.get(nodo.id)
        if not hijas:
            return schedule.tareas.get(nodo.id)

        calculadas = [t for t in (resolver(h) for h in hijas) if t is not None]
        if not calculadas:
            return None

        envolvente = ScheduledTask(
            id=nodo.id,
            inicio=min(t.inicio for t in calculadas),
            fin=max(t.fin for t in calculadas),
            es_resumen=True,
        )
        schedule.tareas[nodo.id] = envolvente
        return envolvente

    for raiz in grupos.get(None, []):
        resolver(raiz)


def _fechas_de_proyecto(schedule: Schedule, arranque: date) -> None:
    if not schedule.tareas:
        schedule.inicio = schedule.fin = arranque
        return
    schedule.inicio = min(t.inicio for t in schedule.tareas.values())
    schedule.fin = max(t.fin for t in schedule.tareas.values())
