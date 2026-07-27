from datetime import date

from app.engine.timeline import barra, construir_grilla


def test_la_grilla_arranca_el_lunes_y_termina_el_viernes():
    grilla = construir_grilla(date(2026, 1, 7), date(2026, 1, 14))
    assert grilla.dias[0] == date(2026, 1, 5)
    assert grilla.dias[-1] == date(2026, 1, 16)
    assert grilla.columnas == 10


def test_solo_hay_columnas_de_dias_habiles():
    grilla = construir_grilla(date(2026, 1, 5), date(2026, 1, 9))
    assert all(d.weekday() < 5 for d in grilla.dias)
    assert grilla.columnas == 5


def test_las_semanas_agrupan_de_a_cinco_dias():
    grilla = construir_grilla(date(2026, 1, 5), date(2026, 1, 16))
    assert [s.dias for s in grilla.semanas] == [5, 5]
    assert grilla.semanas[0].etiqueta == "S02"
    assert grilla.semanas[1].numero == 3


def test_la_barra_cubre_las_columnas_de_la_tarea():
    grilla = construir_grilla(date(2026, 1, 5), date(2026, 1, 16))
    assert barra(grilla, date(2026, 1, 5), date(2026, 1, 7)) == (1, 4)
    assert barra(grilla, date(2026, 1, 12), date(2026, 1, 12)) == (6, 7)


def test_una_barra_fuera_del_rango_no_se_pinta():
    grilla = construir_grilla(date(2026, 1, 5), date(2026, 1, 9))
    assert barra(grilla, date(2026, 2, 2), date(2026, 2, 3)) is None


def test_cruce_de_anio_iso_no_repite_semanas():
    grilla = construir_grilla(date(2025, 12, 22), date(2026, 1, 9))
    numeros = [(s.anio, s.numero) for s in grilla.semanas]
    assert len(numeros) == len(set(numeros))
    assert (2026, 1) in numeros


def test_los_meses_cubren_todas_las_columnas():
    grilla = construir_grilla(date(2026, 1, 26), date(2026, 2, 6))
    assert sum(m.dias for m in grilla.meses) == grilla.columnas
    assert [m.etiqueta for m in grilla.meses] == ["ene 2026", "feb 2026"]
