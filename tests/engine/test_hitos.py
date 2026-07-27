"""Hitos: duración 0, no consumen días del cronograma."""

from datetime import date

from app.engine import calcular, marcar
from app.engine.types import DependencyEdge, TaskNode

INICIO = date(2026, 1, 5)  # lunes


def tarea(id_, duracion=1, parent=None):
    return TaskNode(id=id_, titulo=f"T{id_}", parent_id=parent, duracion=duracion)


def test_un_hito_arranca_y_termina_el_mismo_dia():
    nodos = [tarea(1, duracion=3), tarea(2, duracion=0)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2)])
    hito = plan.get(2)
    assert hito.inicio == hito.fin == date(2026, 1, 8)
    assert hito.es_hito


def test_el_hito_no_agrega_un_dia_a_la_cadena():
    """Con y sin hito intermedio, la tarea final arranca el mismo día."""
    con_hito = calcular(
        INICIO,
        [tarea(1, duracion=3), tarea(2, duracion=0), tarea(3, duracion=2)],
        [DependencyEdge(1, 2), DependencyEdge(2, 3)],
    )
    sin_hito = calcular(
        INICIO,
        [tarea(1, duracion=3), tarea(3, duracion=2)],
        [DependencyEdge(1, 3)],
    )
    assert con_hito.get(3).inicio == sin_hito.get(3).inicio == date(2026, 1, 8)
    assert con_hito.get(3).fin == sin_hito.get(3).fin


def test_hito_con_varias_predecesoras_cae_tras_la_mas_tardia():
    nodos = [tarea(1, duracion=2), tarea(2, duracion=6), tarea(3, duracion=0)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 3), DependencyEdge(2, 3)])
    assert plan.get(2).fin == date(2026, 1, 12)
    assert plan.get(3).inicio == date(2026, 1, 13)


def test_hito_sin_predecesoras_cae_en_el_inicio_del_proyecto():
    plan = calcular(INICIO, [tarea(1, duracion=0)], [])
    assert plan.get(1).inicio == plan.get(1).fin == INICIO


def test_hito_en_fin_de_semana_se_corre_al_lunes():
    nodos = [tarea(1, duracion=5), tarea(2, duracion=0)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2)])
    assert plan.get(1).fin == date(2026, 1, 9)  # viernes
    assert plan.get(2).inicio == date(2026, 1, 12)  # lunes


def test_hito_con_lag_espera_como_cualquier_sucesora():
    """El salto lo define la predecesora: acá es una tarea normal, así que suma 1 + lag."""
    nodos = [tarea(1, duracion=2), tarea(2, duracion=0)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2, lag=3)])
    assert plan.get(1).fin == date(2026, 1, 6)
    assert plan.get(2).inicio == date(2026, 1, 12)


def test_el_lag_tras_un_hito_no_suma_el_dia_del_hito():
    nodos = [tarea(1, duracion=2), tarea(2, duracion=0), tarea(3, duracion=1)]
    aristas = [DependencyEdge(1, 2), DependencyEdge(2, 3, lag=2)]
    plan = calcular(INICIO, nodos, aristas)
    assert plan.get(2).inicio == date(2026, 1, 7)
    assert plan.get(3).inicio == date(2026, 1, 9)


def test_el_hito_entra_en_la_ruta_critica():
    nodos = [tarea(1, duracion=3), tarea(2, duracion=0), tarea(3, duracion=2), tarea(4, duracion=1)]
    aristas = [DependencyEdge(1, 2), DependencyEdge(2, 3)]
    plan = marcar(calcular(INICIO, nodos, aristas), nodos, aristas)
    assert plan.get(2).critica and plan.get(2).holgura == 0
    assert not plan.get(4).critica


def test_el_resumen_envuelve_a_sus_hitos():
    nodos = [tarea(1), tarea(2, duracion=4, parent=1), tarea(3, duracion=0, parent=1)]
    plan = calcular(INICIO, nodos, [DependencyEdge(2, 3)])
    assert plan.get(1).inicio == INICIO
    assert plan.get(1).fin == plan.get(3).fin == date(2026, 1, 9)
