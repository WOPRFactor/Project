"""Desvío contra la línea base. Motor puro: sin DB y sin server."""

from datetime import date

from app.engine.comparar import Congelada, comparar, dias_habiles_con_signo, por_ambito


def c(id_, fin, inicio=None, ambito="proyecto", titulo=None):
    return Congelada(
        task_id=id_, titulo=titulo or f"T{id_}",
        inicio=inicio or date(2026, 1, 5), fin=fin, ambito=ambito,
    )


def uno(base, actual, task_id=1):
    return {d.task_id: d for d in comparar(base, actual)}[task_id]


# --- la aritmética con signo ---

def test_la_distancia_cuenta_dias_habiles():
    # lunes 5 → viernes 9 de enero de 2026
    assert dias_habiles_con_signo(date(2026, 1, 5), date(2026, 1, 9)) == 4


def test_saltea_el_fin_de_semana():
    # viernes 9 → lunes 12: un solo día hábil de distancia
    assert dias_habiles_con_signo(date(2026, 1, 9), date(2026, 1, 12)) == 1


def test_hacia_atras_da_negativo():
    assert dias_habiles_con_signo(date(2026, 1, 9), date(2026, 1, 5)) == -4


def test_la_misma_fecha_no_es_desvio():
    assert dias_habiles_con_signo(date(2026, 1, 5), date(2026, 1, 5)) == 0


# --- los casos del criterio de hecho ---

def test_una_tarea_atrasada_da_positivo():
    """Positivo = atrasado: se tiene que poder leer sin pensar."""
    desvio = uno([c(1, date(2026, 1, 9))], [c(1, date(2026, 1, 16))])
    assert desvio.dias == 5 and desvio.atrasada


def test_una_tarea_adelantada_da_negativo():
    desvio = uno([c(1, date(2026, 1, 16))], [c(1, date(2026, 1, 9))])
    assert desvio.dias == -5 and desvio.adelantada


def test_una_tarea_sin_cambios_da_cero():
    desvio = uno([c(1, date(2026, 1, 9))], [c(1, date(2026, 1, 9))])
    assert desvio.dias == 0
    assert not desvio.atrasada and not desvio.adelantada


def test_una_tarea_nueva_no_es_un_atraso():
    """Alcance agregado después de aprobar es otra conversación, no un desvío."""
    desvio = uno([], [c(1, date(2026, 2, 2))])
    assert desvio.es_nueva and desvio.dias == 0
    assert not desvio.comparable


def test_una_tarea_borrada_se_reporta_igual():
    """Estaba comprometida y ya no está: eso el informe lo tiene que decir."""
    desvios = comparar([c(1, date(2026, 1, 9), titulo="Prometida")], [])
    assert len(desvios) == 1
    assert desvios[0].fue_borrada and desvios[0].titulo == "Prometida"


def test_las_borradas_van_al_final():
    desvios = comparar(
        [c(1, date(2026, 1, 9)), c(2, date(2026, 1, 9))],
        [c(2, date(2026, 1, 9))],
    )
    assert [d.task_id for d in desvios] == [2, 1]
    assert desvios[-1].fue_borrada


def test_sin_fecha_no_se_inventa_desvio():
    desvio = uno([Congelada(1, "T1")], [Congelada(1, "T1")])
    assert desvio.dias == 0


def test_se_respeta_el_orden_del_cronograma_actual():
    desvios = comparar(
        [c(1, date(2026, 1, 9)), c(2, date(2026, 1, 9))],
        [c(2, date(2026, 1, 9)), c(1, date(2026, 1, 9))],
    )
    assert [d.task_id for d in desvios] == [2, 1]


# --- por ámbito ---

def test_el_desvio_del_bloque_es_el_de_su_fin_no_la_suma():
    """Cinco tareas atrasadas cinco días en paralelo mueven el bloque cinco, no 25."""
    base = [c(1, date(2026, 1, 9)), c(2, date(2026, 1, 9))]
    actual = [c(1, date(2026, 1, 16)), c(2, date(2026, 1, 16))]
    assert por_ambito(base, actual) == {"proyecto": 5}


def test_cada_ambito_se_mide_por_su_cuenta():
    base = [c(1, date(2026, 1, 9)), c(2, date(2026, 3, 6), ambito="seguimiento")]
    actual = [c(1, date(2026, 1, 9)), c(2, date(2026, 3, 13), ambito="seguimiento")]
    resultado = por_ambito(base, actual)
    assert resultado["proyecto"] == 0
    assert resultado["seguimiento"] == 5


def test_un_ambito_que_no_estaba_en_la_base_no_reporta_desvio():
    base = [c(1, date(2026, 1, 9))]
    actual = [c(1, date(2026, 1, 9)), c(2, date(2026, 4, 3), ambito="control")]
    assert "control" not in por_ambito(base, actual)


def test_sin_nada_que_comparar_no_rompe():
    assert comparar([], []) == []
    assert por_ambito([], []) == {}
