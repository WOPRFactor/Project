"""Backward pass: holgura por tarea y ruta crítica.

Se corre sobre un cronograma ya calculado por scheduler.calcular(). Una hoja es
crítica cuando su holgura es cero: atrasarla atrasa el fin del proyecto.
"""

from __future__ import annotations

from . import graph
from .calendar import contar_habiles, sumar_habiles
from .types import DependencyEdge, Schedule, TaskNode


def marcar(
    schedule: Schedule,
    nodos: list[TaskNode],
    aristas: list[DependencyEdge],
) -> Schedule:
    """Anota holgura y `critica` sobre el cronograma recibido y lo devuelve."""
    if not schedule.tareas or schedule.fin is None:
        return schedule

    grupos = graph.hijas_por_padre(nodos)
    por_id = {n.id: n for n in nodos}
    hojas = [n for n in nodos if not graph.es_resumen(n, grupos)]
    ids_hoja = {n.id for n in hojas}
    relevantes = [
        a for a in aristas if a.predecessor_id in ids_hoja and a.successor_id in ids_hoja
    ]

    _holgura_de_hojas(schedule, hojas, relevantes, por_id)
    _holgura_de_resumenes(schedule, grupos)
    return schedule


def _holgura_de_hojas(
    schedule: Schedule,
    hojas: list[TaskNode],
    aristas: list[DependencyEdge],
    por_id: dict[int, TaskNode],
) -> None:
    salientes = graph.sucesoras_por_tarea(aristas)
    orden = graph.orden_topologico([n.id for n in hojas], aristas)
    fin_proyecto = max(schedule.tareas[i].fin for i in orden)
    inicio_tardio: dict[int, object] = {}

    for task_id in reversed(orden):
        tarea = schedule.tareas[task_id]
        fin_tardio = fin_proyecto
        for arista in salientes.get(task_id, []):
            tardio_sucesora = inicio_tardio[arista.successor_id]
            fin_tardio = min(fin_tardio, sumar_habiles(tardio_sucesora, -(1 + arista.lag)))

        duracion = max(por_id[task_id].duracion, 1)
        inicio_tardio[task_id] = sumar_habiles(fin_tardio, -(duracion - 1))
        tarea.holgura = max(contar_habiles(tarea.fin, fin_tardio) - 1, 0)
        tarea.critica = tarea.holgura == 0


def _holgura_de_resumenes(
    schedule: Schedule, grupos: dict[int | None, list[TaskNode]]
) -> None:
    """Un resumen hereda la menor holgura de sus descendientes y su criticidad."""

    def resolver(nodo: TaskNode) -> tuple[int, bool] | None:
        hijas = grupos.get(nodo.id)
        tarea = schedule.tareas.get(nodo.id)
        if not hijas:
            return (tarea.holgura, tarea.critica) if tarea else None

        resultados = [r for r in (resolver(h) for h in hijas) if r is not None]
        if not resultados or tarea is None:
            return None

        tarea.holgura = min(h for h, _ in resultados)
        tarea.critica = any(c for _, c in resultados)
        return tarea.holgura, tarea.critica

    for raiz in grupos.get(None, []):
        resolver(raiz)
