import pytest

from app.engine.graph import (
    es_resumen,
    hijas_por_padre,
    orden_jerarquico,
    orden_topologico,
    validar_arbol,
    validar_dependencias,
)
from app.engine.types import (
    CycleError,
    DanglingReferenceError,
    DependencyEdge,
    SummaryDependencyError,
    TaskNode,
    TreeError,
)


def nodo(id_, parent=None, orden=0):
    return TaskNode(id=id_, titulo=f"T{id_}", parent_id=parent, orden=orden)


def test_orden_jerarquico_respeta_arbol_y_orden():
    nodos = [nodo(1), nodo(2, parent=1, orden=1), nodo(3, parent=1, orden=0), nodo(4)]
    assert [n.id for n in orden_jerarquico(nodos)] == [1, 3, 2, 4]


def test_es_resumen_solo_si_tiene_hijas():
    nodos = [nodo(1), nodo(2, parent=1)]
    grupos = hijas_por_padre(nodos)
    assert es_resumen(nodos[0], grupos)
    assert not es_resumen(nodos[1], grupos)


def test_arbol_con_padre_inexistente_falla():
    with pytest.raises(TreeError):
        validar_arbol([nodo(1, parent=99)])


def test_arbol_con_ciclo_de_jerarquia_falla():
    with pytest.raises(TreeError):
        validar_arbol([nodo(1, parent=2), nodo(2, parent=1)])


def test_dependencia_a_tarea_inexistente_falla():
    with pytest.raises(DanglingReferenceError):
        validar_dependencias([nodo(1)], [DependencyEdge(1, 42)])


def test_dependencia_sobre_resumen_falla():
    nodos = [nodo(1), nodo(2, parent=1), nodo(3)]
    with pytest.raises(SummaryDependencyError):
        validar_dependencias(nodos, [DependencyEdge(1, 3)])


def test_dependencia_de_una_tarea_consigo_misma_falla():
    with pytest.raises(CycleError):
        validar_dependencias([nodo(1)], [DependencyEdge(1, 1)])


def test_toposort_ordena_predecesoras_primero():
    orden = orden_topologico([1, 2, 3], [DependencyEdge(3, 2), DependencyEdge(2, 1)])
    assert orden == [3, 2, 1]


def test_toposort_detecta_ciclo_y_reporta_los_nodos():
    with pytest.raises(CycleError) as error:
        orden_topologico([1, 2, 3], [DependencyEdge(1, 2), DependencyEdge(2, 3), DependencyEdge(3, 1)])
    assert set(error.value.ciclo) == {1, 2, 3}
