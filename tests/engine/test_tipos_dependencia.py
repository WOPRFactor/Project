"""Inicio→Inicio y Fin→Fin.

SS nace de un caso real: en un traspaso operativo, «supervisión en tiempo real»
corre *durante* la ejecución rutinaria, no después. Declararlo FS empujaba el
proyecto un mes y medio.
"""

from datetime import date

import pytest

from app.engine import calcular, marcar
from app.engine.types import DependencyEdge, TaskNode, TipoDependencia

INICIO = date(2026, 1, 5)  # lunes
FS, SS, FF = TipoDependencia.FS, TipoDependencia.SS, TipoDependencia.FF


def tarea(id_, duracion=1, parent=None):
    return TaskNode(id=id_, titulo=f"T{id_}", parent_id=parent, duracion=duracion)


def test_ss_las_hace_arrancar_juntas():
    nodos = [tarea(1, duracion=10), tarea(2, duracion=4)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2, tipo=SS)])
    assert plan.get(1).inicio == plan.get(2).inicio == INICIO
    assert plan.get(2).fin == date(2026, 1, 8)


def test_ss_con_lag_arranca_despues():
    nodos = [tarea(1, duracion=10), tarea(2, duracion=2)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2, lag=3, tipo=SS)])
    assert plan.get(2).inicio == date(2026, 1, 8)


def test_ss_no_alarga_el_proyecto():
    """El caso que motivó todo: en serie dura el doble que en paralelo."""
    nodos = [tarea(1, duracion=30), tarea(2, duracion=30)]
    en_serie = calcular(INICIO, nodos, [DependencyEdge(1, 2, tipo=FS)])
    en_paralelo = calcular(INICIO, nodos, [DependencyEdge(1, 2, tipo=SS)])
    assert en_paralelo.fin == en_serie.get(1).fin
    assert (en_serie.fin - en_paralelo.fin).days == 42


def test_ff_las_hace_terminar_juntas():
    nodos = [tarea(1, duracion=10), tarea(2, duracion=3)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2, tipo=FF)])
    assert plan.get(1).fin == plan.get(2).fin == date(2026, 1, 16)
    assert plan.get(2).inicio == date(2026, 1, 14)


def test_ff_con_lag_termina_despues():
    nodos = [tarea(1, duracion=5), tarea(2, duracion=2)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2, lag=3, tipo=FF)])
    assert plan.get(1).fin == date(2026, 1, 9)
    assert plan.get(2).fin == date(2026, 1, 14)


def test_ff_no_arranca_antes_del_proyecto():
    nodos = [tarea(1, duracion=2), tarea(2, duracion=30)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2, tipo=FF)])
    assert plan.get(2).inicio == INICIO


def test_se_pueden_mezclar_los_tres_tipos():
    nodos = [tarea(1, duracion=10), tarea(2, duracion=4), tarea(3, duracion=2), tarea(4, duracion=1)]
    aristas = [
        DependencyEdge(1, 2, tipo=SS),   # arranca con la 1
        DependencyEdge(1, 3, tipo=FF),   # termina con la 1
        DependencyEdge(1, 4, tipo=FS),   # arranca cuando termina la 1
    ]
    plan = calcular(INICIO, nodos, aristas)
    assert plan.get(2).inicio == plan.get(1).inicio
    assert plan.get(3).fin == plan.get(1).fin
    assert plan.get(4).inicio == date(2026, 1, 19)


def test_la_holgura_respeta_el_tipo_ss():
    nodos = [tarea(1, duracion=10), tarea(2, duracion=2), tarea(3, duracion=1)]
    aristas = [DependencyEdge(1, 2, tipo=SS), DependencyEdge(1, 3, tipo=FS)]
    plan = marcar(calcular(INICIO, nodos, aristas), nodos, aristas)
    assert plan.get(1).critica
    assert plan.get(3).critica          # arranca recién cuando la 1 termina
    # la 2 arranca con la 1 pero dura 2 días y nada depende de ella: flota hasta
    # el fin del proyecto (19/01), no hasta el fin de la 1
    assert plan.get(2).fin == date(2026, 1, 6)
    assert plan.get(2).holgura == 9


def test_la_holgura_respeta_el_tipo_ff():
    nodos = [tarea(1, duracion=10), tarea(2, duracion=3)]
    aristas = [DependencyEdge(1, 2, tipo=FF)]
    plan = marcar(calcular(INICIO, nodos, aristas), nodos, aristas)
    assert plan.get(1).critica and plan.get(2).critica
    assert plan.get(2).holgura == 0


def test_un_ciclo_con_ss_tambien_se_detecta():
    from app.engine.types import CycleError

    nodos = [tarea(1, duracion=2), tarea(2, duracion=2)]
    with pytest.raises(CycleError):
        calcular(INICIO, nodos, [DependencyEdge(1, 2, tipo=SS), DependencyEdge(2, 1, tipo=SS)])


def test_por_default_sigue_siendo_fin_a_inicio():
    nodos = [tarea(1, duracion=3), tarea(2, duracion=2)]
    plan = calcular(INICIO, nodos, [DependencyEdge(1, 2)])
    assert plan.get(2).inicio == date(2026, 1, 8)
