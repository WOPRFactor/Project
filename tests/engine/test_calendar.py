from datetime import date

from app.engine.calendar import (
    anterior_habil,
    contar_habiles,
    es_habil,
    fin_desde_inicio,
    siguiente_habil,
    sumar_habiles,
)

LUNES = date(2026, 1, 5)
VIERNES = date(2026, 1, 9)
SABADO = date(2026, 1, 10)


def test_reconoce_fin_de_semana():
    assert es_habil(LUNES)
    assert es_habil(VIERNES)
    assert not es_habil(SABADO)
    assert not es_habil(date(2026, 1, 11))


def test_siguiente_y_anterior_habil():
    assert siguiente_habil(LUNES) == LUNES
    assert siguiente_habil(SABADO) == date(2026, 1, 12)
    assert anterior_habil(SABADO) == VIERNES


def test_sumar_habiles_saltea_el_fin_de_semana():
    assert sumar_habiles(VIERNES, 1) == date(2026, 1, 12)
    assert sumar_habiles(LUNES, 5) == date(2026, 1, 12)
    assert sumar_habiles(LUNES, 0) == LUNES


def test_sumar_habiles_hacia_atras():
    assert sumar_habiles(date(2026, 1, 12), -1) == VIERNES
    assert sumar_habiles(VIERNES, -4) == LUNES


def test_fin_desde_inicio_cuenta_el_primer_dia():
    assert fin_desde_inicio(LUNES, 1) == LUNES
    assert fin_desde_inicio(LUNES, 5) == VIERNES
    assert fin_desde_inicio(LUNES, 6) == date(2026, 1, 12)


def test_contar_habiles_es_inclusivo():
    assert contar_habiles(LUNES, LUNES) == 1
    assert contar_habiles(LUNES, VIERNES) == 5
    assert contar_habiles(LUNES, date(2026, 1, 12)) == 6
    assert contar_habiles(VIERNES, LUNES) == 0
