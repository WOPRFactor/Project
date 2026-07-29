"""Estructura del árbol de tareas y del grafo de dependencias.

Todo lo que valida y ordena vive acá; el cálculo de fechas vive en scheduler.py.
El grafo se trata como input hostil: se valida antes de recorrerlo, así una
dependencia mal cargada da un error claro y nunca un loop infinito.
"""

from __future__ import annotations

from collections import defaultdict, deque

from .types import (
    CycleError,
    DanglingReferenceError,
    DependencyEdge,
    SummaryDependencyError,
    TaskNode,
    TreeError,
)


def hijas_por_padre(nodos: list[TaskNode]) -> dict[int | None, list[TaskNode]]:
    """Agrupa las tareas por padre, cada grupo ordenado por `orden` y luego por id."""
    grupos: dict[int | None, list[TaskNode]] = defaultdict(list)
    for nodo in nodos:
        grupos[nodo.parent_id].append(nodo)
    for hijas in grupos.values():
        hijas.sort(key=lambda n: (n.orden, n.id))
    return grupos


def es_resumen(nodo: TaskNode, grupos: dict[int | None, list[TaskNode]]) -> bool:
    return bool(grupos.get(nodo.id))


def validar_arbol(nodos: list[TaskNode]) -> None:
    """Verifica que cada padre exista y que la jerarquía no tenga ciclos.

    La existencia se chequea en cada paso de la subida, no solo en el padre
    directo: un ancestro colgante también tiene que dar TreeError, no un KeyError.
    """
    por_id = {n.id: n for n in nodos}
    for nodo in nodos:
        if nodo.parent_id is None:
            continue
        visto = {nodo.id}
        actual = nodo
        while actual.parent_id is not None:
            padre = por_id.get(actual.parent_id)
            if padre is None:
                raise TreeError(
                    f"La tarea {actual.id} cuelga de un padre inexistente ({actual.parent_id})"
                )
            if padre.id in visto:
                raise TreeError(f"La jerarquía de la tarea {nodo.id} forma un ciclo")
            visto.add(padre.id)
            actual = padre


def orden_jerarquico(nodos: list[TaskNode]) -> list[TaskNode]:
    """Recorrido en profundidad del árbol, respetando `orden` en cada nivel."""
    grupos = hijas_por_padre(nodos)
    salida: list[TaskNode] = []

    def bajar(padre: int | None) -> None:
        for hija in grupos.get(padre, []):
            salida.append(hija)
            bajar(hija.id)

    bajar(None)
    return salida


def validar_dependencias(
    nodos: list[TaskNode], aristas: list[DependencyEdge]
) -> None:
    """Rechaza referencias colgantes y dependencias que toquen tareas resumen."""
    por_id = {n.id: n for n in nodos}
    grupos = hijas_por_padre(nodos)
    for arista in aristas:
        for extremo in (arista.predecessor_id, arista.successor_id):
            nodo = por_id.get(extremo)
            if nodo is None:
                raise DanglingReferenceError(extremo)
            if es_resumen(nodo, grupos):
                raise SummaryDependencyError(extremo)
        if arista.predecessor_id == arista.successor_id:
            raise CycleError([arista.predecessor_id, arista.predecessor_id])


def orden_topologico(ids: list[int], aristas: list[DependencyEdge]) -> list[int]:
    """Ordena las tareas para que toda predecesora venga antes que su sucesora.

    Kahn: si al final quedan nodos sin emitir, hay un ciclo y se reporta con las
    tareas involucradas.
    """
    pendientes: dict[int, int] = {i: 0 for i in ids}
    sucesoras: dict[int, list[int]] = defaultdict(list)
    for arista in aristas:
        sucesoras[arista.predecessor_id].append(arista.successor_id)
        pendientes[arista.successor_id] += 1

    cola = deque(sorted(i for i, grado in pendientes.items() if grado == 0))
    salida: list[int] = []
    while cola:
        actual = cola.popleft()
        salida.append(actual)
        for siguiente in sucesoras.get(actual, []):
            pendientes[siguiente] -= 1
            if pendientes[siguiente] == 0:
                cola.append(siguiente)

    if len(salida) != len(ids):
        atrapados = [i for i in ids if i not in set(salida)]
        raise CycleError(_extraer_ciclo(atrapados, aristas))
    return salida


def _extraer_ciclo(atrapados: list[int], aristas: list[DependencyEdge]) -> list[int]:
    """Devuelve un ciclo concreto dentro de los nodos que el toposort no pudo emitir."""
    dentro = set(atrapados)
    sucesoras: dict[int, list[int]] = defaultdict(list)
    for arista in aristas:
        if arista.predecessor_id in dentro and arista.successor_id in dentro:
            sucesoras[arista.predecessor_id].append(arista.successor_id)

    inicio = min(atrapados)
    camino: list[int] = []
    visto: set[int] = set()
    actual = inicio
    while actual not in visto:
        visto.add(actual)
        camino.append(actual)
        siguientes = sucesoras.get(actual)
        if not siguientes:
            return camino
        actual = siguientes[0]
    return camino[camino.index(actual) :] + [actual]


def predecesoras_por_tarea(aristas: list[DependencyEdge]) -> dict[int, list[DependencyEdge]]:
    entrantes: dict[int, list[DependencyEdge]] = defaultdict(list)
    for arista in aristas:
        entrantes[arista.successor_id].append(arista)
    return entrantes


def sucesoras_por_tarea(aristas: list[DependencyEdge]) -> dict[int, list[DependencyEdge]]:
    salientes: dict[int, list[DependencyEdge]] = defaultdict(list)
    for arista in aristas:
        salientes[arista.predecessor_id].append(arista)
    return salientes
