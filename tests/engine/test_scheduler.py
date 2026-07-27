from datetime import date

import pytest

from app.engine import calcular
from app.engine.types import CycleError, DependencyEdge, TaskNode

INICIO = date(2026, 1, 5)  # lunes


def tarea(id_, duracion=1, parent=None, snet=None, orden=0):
    return TaskNode(id=id_, titulo=f"T{id_}", parent_id=parent, duracion=duracion, snet=snet, orden=orden)


def test_tarea_sola_arranca_con_el_proyecto():
    plan = calcular(INICIO, [tarea(1, duracion=3)], [])
    assert plan.get(1).inicio == INICIO
    assert plan.get(1).fin == date(2026, 1, 7)
    assert plan.inicio == INICIO and plan.fin == date(2026, 1, 7)


def test_inicio_de_proyecto_en_fin_de_semana_se_corre_al_lunes():
    plan = calcular(date(2026, 1, 10), [tarea(1)], [])
    assert plan.get(1).inicio == date(2026, 1, 12)


def test_cadena_simple_encadena_al_dia_habil_siguiente():
    nodos = [tarea(1, duracion=3), tarea(2, duracion=2)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2)])
    assert plan.get(1).fin == date(2026, 1, 7)
    assert plan.get(2).inicio == date(2026, 1, 8)
    assert plan.get(2).fin == date(2026, 1, 9)


def test_la_duracion_saltea_el_fin_de_semana():
    nodos = [tarea(1, duracion=5), tarea(2, duracion=1)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2)])
    assert plan.get(1).fin == date(2026, 1, 9)  # viernes
    assert plan.get(2).inicio == date(2026, 1, 12)  # lunes


def test_lag_positivo_empuja_el_arranque():
    nodos = [tarea(1, duracion=3), tarea(2, duracion=1)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2, lag=2)])
    assert plan.get(2).inicio == date(2026, 1, 12)


def test_lag_negativo_solapa_las_tareas():
    nodos = [tarea(1, duracion=3), tarea(2, duracion=1)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2, lag=-1)])
    assert plan.get(2).inicio == plan.get(1).fin == date(2026, 1, 7)


def test_lag_negativo_no_arranca_antes_del_proyecto():
    nodos = [tarea(1, duracion=1), tarea(2, duracion=1)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2, lag=-10)])
    assert plan.get(2).inicio == INICIO


def test_diamante_toma_la_predecesora_mas_tardia():
    nodos = [tarea(1, duracion=1), tarea(2, duracion=5), tarea(3, duracion=2), tarea(4, duracion=1)]
    aristas = [
        DependencyEdge(1, 2), DependencyEdge(1, 3),
        DependencyEdge(2, 4), DependencyEdge(3, 4),
    ]
    plan = calcular(INICIO, nodos, aristas)
    assert plan.get(2).fin == date(2026, 1, 12)
    assert plan.get(4).inicio == date(2026, 1, 13)


def test_snet_empuja_el_arranque():
    plan = calcular(INICIO, [tarea(1, duracion=2, snet=date(2026, 1, 14))], [])
    assert plan.get(1).inicio == date(2026, 1, 14)
    assert plan.get(1).fin == date(2026, 1, 15)


def test_snet_no_adelanta_una_tarea_dependiente():
    nodos = [tarea(1, duracion=3), tarea(2, duracion=1, snet=INICIO)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2)])
    assert plan.get(2).inicio == date(2026, 1, 8)


def test_rollup_multinivel_envuelve_a_las_hojas():
    nodos = [
        tarea(1),                                   # resumen raíz
        tarea(2, parent=1),                         # resumen intermedio
        tarea(3, duracion=2, parent=2),
        tarea(4, duracion=4, parent=2),
        tarea(5, duracion=1, parent=1),
    ]
    plan = calcular(INICIO, nodos, [DependencyEdge(3, 4)])
    assert plan.get(4).inicio == date(2026, 1, 7)
    assert plan.get(2).inicio == INICIO
    assert plan.get(2).fin == plan.get(4).fin == date(2026, 1, 12)
    assert plan.get(1).es_resumen and plan.get(1).fin == date(2026, 1, 12)


def test_la_duracion_del_resumen_se_ignora():
    nodos = [tarea(1, duracion=99), tarea(2, duracion=2, parent=1)]
    plan = calcular(INICIO, nodos, [])
    assert plan.get(1).fin == plan.get(2).fin == date(2026, 1, 6)


def test_ciclo_se_rechaza_sin_colgar():
    nodos = [tarea(1), tarea(2)]
    with pytest.raises(CycleError):
        calcular(INICIO, nodos, [DependencyEdge(1, 2), DependencyEdge(2, 1)])


def test_proyecto_sin_tareas_devuelve_cronograma_vacio():
    plan = calcular(INICIO, [], [])
    assert plan.tareas == {}
