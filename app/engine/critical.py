"""Backward pass: holgura por tarea y ruta crítica.

Se corre sobre un cronograma ya calculado por scheduler.calcular(). Una hoja es
crítica cuando su holgura es cero: atrasarla atrasa el fin del proyecto.
"""

from __future__ import annotations
from datetime import date


from . import graph
from .calendar import contar_habiles, sumar_habiles
from .scheduler import salto_tras
from .types import DependencyEdge, Escenario, Schedule, TaskNode, TipoDependencia


def marcar(
    schedule: Schedule,
    nodos: list[TaskNode],
    aristas: list[DependencyEdge],
    tope_por_tarea: dict[int, date] | None = None,
    escenario: Escenario = Escenario.PROBABLE,
) -> Schedule:
    """Anota holgura y `critica` sobre el cronograma recibido y lo devuelve.

    `tope_por_tarea` es la fecha contra la que se mide la holgura de cada tarea que
    no tiene sucesoras. Por default es el fin del proyecto, pero medir todo contra
    él infla los márgenes: si una actividad de acompañamiento estira el fin seis
    meses, el resto del plan aparece con seis meses de comodidad que no tiene. El
    llamador puede pasar el fin del bloque al que pertenece cada tarea.
    """
    if not schedule.tareas or schedule.fin is None:
        return schedule

    grupos = graph.hijas_por_padre(nodos)
    por_id = {n.id: n for n in nodos}
    hojas = [n for n in nodos if not graph.es_resumen(n, grupos)]
    ids_hoja = {n.id for n in hojas}
    relevantes = [
        a for a in aristas if a.predecessor_id in ids_hoja and a.successor_id in ids_hoja
    ]

    _holgura_de_hojas(schedule, hojas, relevantes, por_id, tope_por_tarea or {}, escenario)
    _holgura_de_resumenes(schedule, grupos)
    return schedule


def _holgura_de_hojas(
    schedule: Schedule,
    hojas: list[TaskNode],
    aristas: list[DependencyEdge],
    por_id: dict[int, TaskNode],
    tope_por_tarea: dict[int, date],
    escenario: Escenario,
) -> None:
    salientes = graph.sucesoras_por_tarea(aristas)
    orden = graph.orden_topologico([n.id for n in hojas], aristas)
    fin_proyecto = max(schedule.tareas[i].fin for i in orden)
    inicio_tardio: dict[int, date] = {}
    fin_tardio_de: dict[int, date] = {}

    for task_id in reversed(orden):
        tarea = schedule.tareas[task_id]
        nodo = por_id[task_id]
        # La misma duración con la que se calculó el cronograma: holgura medida
        # sobre un escenario con la duración de otro daría márgenes falsos.
        duracion = max(nodo.duracion_en(escenario), 1)

        fin_tardio = tope_por_tarea.get(task_id, fin_proyecto)
        for arista in salientes.get(task_id, []):
            fin_tardio = min(
                fin_tardio,
                _tope_por_sucesora(arista, nodo, duracion, inicio_tardio, fin_tardio_de),
            )

        fin_tardio_de[task_id] = fin_tardio
        inicio_tardio[task_id] = sumar_habiles(fin_tardio, -(duracion - 1))
        tarea.holgura = max(contar_habiles(tarea.fin, fin_tardio) - 1, 0)
        tarea.critica = tarea.holgura == 0


def _tope_por_sucesora(
    arista: DependencyEdge,
    nodo: TaskNode,
    duracion: int,
    inicio_tardio: dict[int, date],
    fin_tardio_de: dict[int, date],
) -> date:
    """Hasta cuándo puede estirarse la predecesora sin mover a esta sucesora."""
    if arista.tipo is TipoDependencia.SS:
        tope_inicio = sumar_habiles(inicio_tardio[arista.successor_id], -arista.lag)
        return sumar_habiles(tope_inicio, duracion - 1)
    if arista.tipo is TipoDependencia.FF:
        return sumar_habiles(fin_tardio_de[arista.successor_id], -arista.lag)
    salto = salto_tras(nodo)
    return sumar_habiles(inicio_tardio[arista.successor_id], -(salto + arista.lag))


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
