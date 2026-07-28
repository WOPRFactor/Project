"""Reparto de pesos. Módulo puro: ni base ni sesión, igual que el motor."""

from app.services.pesos import (
    NodoPeso,
    absolutos,
    avance_ponderado,
    niveles,
    repartir,
    repartir_parejo,
    repartir_por_duracion,
)


def test_un_nivel_sin_pesos_queda_parejo():
    assert repartir([None, None, None, None]) == [25.0, 25.0, 25.0, 25.0]


def test_lo_declarado_se_respeta_y_el_resto_se_reparte():
    assert repartir([60, None, None]) == [60.0, 20.0, 20.0]


def test_un_nivel_completo_se_deja_como_está():
    assert repartir([20, 30, 50]) == [20.0, 30.0, 50.0]


def test_un_nivel_pasado_de_100_se_normaliza():
    """Que no cierre se avisa aparte; acá no puede salir un avance del 120%."""
    efectivos = repartir([60, 60])
    assert efectivos == [50.0, 50.0]
    assert sum(efectivos) == 100


def test_un_nivel_corto_sin_hermanas_en_blanco_tambien_se_normaliza():
    assert sum(repartir([30, 30])) == 100


def test_todo_en_cero_cae_en_el_reparto_parejo():
    assert repartir([0, 0]) == [50.0, 50.0]


def test_un_nivel_vacío_no_rompe():
    assert repartir([]) == []


# --- cierre de la cuenta ---

def test_un_nivel_declarado_al_100_cierra():
    nivel = niveles([NodoPeso(1, None, 40), NodoPeso(2, None, 60)])[0]
    assert nivel.cierra and nivel.diferencia == 0


def test_un_nivel_declarado_de_menos_no_cierra():
    nivel = niveles([NodoPeso(1, None, 40), NodoPeso(2, None, 30)])[0]
    assert not nivel.cierra and nivel.diferencia == -30


def test_un_nivel_pasado_no_cierra():
    nivel = niveles([NodoPeso(1, None, 70), NodoPeso(2, None, 60)])[0]
    assert not nivel.cierra and nivel.diferencia == 30


def test_con_hermanas_en_blanco_cierra_solo():
    nivel = niveles([NodoPeso(1, None, 40), NodoPeso(2, None, None)])[0]
    assert nivel.cierra and nivel.sin_declarar == 1


def test_avisa_cuando_no_queda_nada_para_las_que_faltan():
    nivel = niveles([NodoPeso(1, None, 100), NodoPeso(2, None, None)])[0]
    assert nivel.cierra and nivel.sin_reparto


def test_hay_un_nivel_por_grupo_de_hermanas():
    nodos = [
        NodoPeso(1, None, 100),
        NodoPeso(2, 1, 50), NodoPeso(3, 1, 50),
    ]
    assert {n.parent_id for n in niveles(nodos)} == {None, 1}


# --- peso absoluto: el ejemplo de Ariel ---

def test_la_etapa_reparte_su_peso_entre_las_subtareas():
    """Etapa con 20% del proyecto y 5 subtareas: cada una al 20% del padre vale 4%."""
    nodos = [
        NodoPeso(1, None, 20), NodoPeso(9, None, 80),
        *[NodoPeso(10 + i, 1, 20) for i in range(5)],
    ]
    peso = absolutos(nodos)
    assert peso[1] == 20.0
    assert [round(peso[10 + i], 3) for i in range(5)] == [4.0] * 5


def test_las_hojas_suman_100():
    nodos = [
        NodoPeso(1, None, 30), NodoPeso(2, None, 70),
        NodoPeso(3, 1, None), NodoPeso(4, 1, None),
        NodoPeso(5, 2, 25), NodoPeso(6, 2, 75),
    ]
    peso = absolutos(nodos)
    assert round(sum(peso[i] for i in (3, 4, 5, 6)), 6) == 100.0


def test_un_arbol_de_tres_niveles_multiplica_bien():
    nodos = [
        NodoPeso(1, None, 100),
        NodoPeso(2, 1, 50),
        NodoPeso(3, 2, 40), NodoPeso(4, 2, 60),
        NodoPeso(5, 1, 50),
    ]
    peso = absolutos(nodos)
    assert round(peso[3], 3) == 20.0 and round(peso[4], 3) == 30.0


def test_una_tarea_suelta_se_lleva_todo():
    assert absolutos([NodoPeso(1, None, None)]) == {1: 100.0}


# --- avance ponderado ---

def test_el_avance_pesa_por_valor_y_no_por_cantidad():
    """Una firma de acta que vale 90 mueve más que veinte tareas de 0,5."""
    nodos = [NodoPeso(1, None, 90), NodoPeso(2, None, 10)]
    assert avance_ponderado(nodos, {1: 100, 2: 0}) == 90
    assert avance_ponderado(nodos, {1: 0, 2: 100}) == 10


def test_el_avance_ignora_a_los_resúmenes_para_no_contar_dos_veces():
    nodos = [NodoPeso(1, None, 100), NodoPeso(2, 1, 50), NodoPeso(3, 1, 50)]
    assert avance_ponderado(nodos, {1: 100, 2: 100, 3: 0}) == 50


def test_sin_tareas_el_avance_es_cero():
    assert avance_ponderado([], {}) == 0


def test_un_proyecto_terminado_da_100():
    nodos = [NodoPeso(1, None, 40), NodoPeso(2, None, 60)]
    assert avance_ponderado(nodos, {1: 100, 2: 100}) == 100


# --- puntos de partida ---

def test_el_reparto_parejo_suma_100_aunque_no_sea_divisible():
    assert repartir_parejo(3) == [34, 33, 33]
    assert sum(repartir_parejo(7)) == 100


def test_el_reparto_por_duracion_le_da_mas_a_la_mas_larga():
    pesos = repartir_por_duracion([10, 30])
    assert pesos == [25, 75] and sum(pesos) == 100


def test_el_reparto_por_duracion_suma_100_con_redondeos_feos():
    assert sum(repartir_por_duracion([1, 1, 1])) == 100


def test_solo_hitos_caen_en_el_reparto_parejo():
    assert repartir_por_duracion([0, 0]) == [50, 50]
