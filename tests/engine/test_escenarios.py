"""Estimación a tres puntos: cuando la duración es una estimación, no un dato."""

from datetime import date

from app.engine import calcular
from app.engine.types import DependencyEdge, Escenario, TaskNode

INICIO = date(2026, 1, 5)


def tarea(id_, duracion=1, opt=None, pes=None, parent=None):
    return TaskNode(
        id=id_, titulo=f"T{id_}", parent_id=parent, duracion=duracion,
        duracion_optimista=opt, duracion_pesimista=pes,
    )


def test_sin_rango_los_tres_escenarios_coinciden():
    nodos = [tarea(1, duracion=5), tarea(2, duracion=3)]
    aristas = [DependencyEdge(1, 2)]
    fines = {e: calcular(INICIO, nodos, aristas, e).fin for e in Escenario}
    assert len(set(fines.values())) == 1


def test_el_rango_abre_la_ventana_de_fin():
    nodos = [tarea(1, duracion=90, opt=40, pes=150)]
    optimista = calcular(INICIO, nodos, [], Escenario.OPTIMISTA).fin
    probable = calcular(INICIO, nodos, [], Escenario.PROBABLE).fin
    pesimista = calcular(INICIO, nodos, [], Escenario.PESIMISTA).fin
    assert optimista < probable < pesimista


def test_la_incertidumbre_se_propaga_por_las_dependencias():
    """Lo que viene detrás de una tarea estimada hereda su incertidumbre."""
    nodos = [tarea(1, duracion=90, opt=40, pes=150), tarea(2, duracion=10)]
    aristas = [DependencyEdge(1, 2)]
    opt = calcular(INICIO, nodos, aristas, Escenario.OPTIMISTA)
    pes = calcular(INICIO, nodos, aristas, Escenario.PESIMISTA)
    assert (pes.get(2).inicio - opt.get(2).inicio).days > 100


def test_un_rango_a_medias_usa_la_probable_del_otro_lado():
    nodos = [tarea(1, duracion=10, opt=5)]     # sin pesimista
    assert calcular(INICIO, nodos, [], Escenario.OPTIMISTA).fin < \
           calcular(INICIO, nodos, [], Escenario.PROBABLE).fin
    assert calcular(INICIO, nodos, [], Escenario.PESIMISTA).fin == \
           calcular(INICIO, nodos, [], Escenario.PROBABLE).fin


def test_un_hito_no_se_estira_en_ningun_escenario():
    nodos = [tarea(1, duracion=5), tarea(2, duracion=0, pes=20)]
    aristas = [DependencyEdge(1, 2)]
    for escenario in Escenario:
        hito = calcular(INICIO, nodos, aristas, escenario).get(2)
        assert hito.inicio == hito.fin


def test_es_estimada_solo_si_declara_rango():
    assert not tarea(1, duracion=5).es_estimada
    assert tarea(2, duracion=5, opt=3).es_estimada
    assert tarea(3, duracion=5, pes=9).es_estimada


def test_el_resumen_envuelve_el_escenario_que_se_calcula():
    nodos = [tarea(1), tarea(2, duracion=10, pes=40, parent=1)]
    probable = calcular(INICIO, nodos, [], Escenario.PROBABLE).get(1)
    pesimista = calcular(INICIO, nodos, [], Escenario.PESIMISTA).get(1)
    assert pesimista.fin > probable.fin
