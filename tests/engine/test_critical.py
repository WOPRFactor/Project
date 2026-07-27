from datetime import date

from app.engine import calcular, marcar
from app.engine.types import DependencyEdge, TaskNode

INICIO = date(2026, 1, 5)


def tarea(id_, duracion=1, parent=None):
    return TaskNode(id=id_, titulo=f"T{id_}", parent_id=parent, duracion=duracion)


def plan_con(nodos, aristas):
    return marcar(calcular(INICIO, nodos, aristas), nodos, aristas)


def test_la_cadena_mas_larga_es_critica():
    nodos = [tarea(1, duracion=3), tarea(2, duracion=2), tarea(3, duracion=1)]
    aristas = [DependencyEdge(1, 2)]
    plan = plan_con(nodos, aristas)
    assert plan.get(1).critica and plan.get(1).holgura == 0
    assert plan.get(2).critica
    assert not plan.get(3).critica
    assert plan.get(3).holgura == 4


def test_holgura_con_lag_positivo():
    nodos = [tarea(1, duracion=2), tarea(2, duracion=2), tarea(3, duracion=1)]
    aristas = [DependencyEdge(1, 2, lag=3)]
    plan = plan_con(nodos, aristas)
    assert plan.get(1).critica and plan.get(2).critica
    assert plan.get(3).holgura > 0


def test_diamante_marca_solo_la_rama_larga():
    nodos = [tarea(1), tarea(2, duracion=5), tarea(3, duracion=2), tarea(4)]
    aristas = [
        DependencyEdge(1, 2), DependencyEdge(1, 3),
        DependencyEdge(2, 4), DependencyEdge(3, 4),
    ]
    plan = plan_con(nodos, aristas)
    assert plan.get(2).critica
    assert not plan.get(3).critica
    assert plan.get(3).holgura == 3
    assert plan.get(1).critica and plan.get(4).critica


def test_el_resumen_hereda_la_criticidad_de_sus_hijas():
    nodos = [tarea(1), tarea(2, duracion=5, parent=1), tarea(3, duracion=1)]
    plan = plan_con(nodos, [])
    assert plan.get(1).es_resumen
    assert plan.get(1).critica
    assert not plan.get(3).critica
