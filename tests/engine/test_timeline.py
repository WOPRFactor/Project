from datetime import date

from app.engine.timeline import ancho_columna, barra, construir_grilla


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


def test_el_ancho_de_columna_se_achica_en_proyectos_largos():
    corto = construir_grilla(date(2026, 1, 5), date(2026, 2, 6))
    largo = construir_grilla(date(2026, 1, 5), date(2026, 12, 31))
    assert ancho_columna(corto.columnas) > ancho_columna(largo.columnas)
    assert ancho_columna(largo.columnas) >= 6
    # un proyecto largo tiene que entrar en un ancho razonable
    assert largo.columnas * ancho_columna(largo.columnas) < 2000


def test_los_meses_cubren_todas_las_columnas():
    grilla = construir_grilla(date(2026, 1, 26), date(2026, 2, 6))
    assert sum(m.dias for m in grilla.meses) == grilla.columnas
    assert [m.etiqueta for m in grilla.meses] == ["ene 2026", "feb 2026"]


# --- flechas entre barras ---

from app.engine.timeline import Extremo, flecha  # noqa: E402


def puntos(texto):
    return [tuple(int(v) for v in p.split(",")) for p in texto.split()]


def test_fs_sale_del_fin_y_entra_por_el_inicio():
    # barra A columnas 1..3 (fin exclusivo 4) fila 0; barra B columnas 5..6 fila 1
    p = puntos(flecha("FS", Extremo(1, 4, 0), Extremo(5, 7, 1), 10, 30, 40))
    assert p[0] == (30, 55)      # fin de A: columna 4 → x=30
    assert p[-1] == (40, 85)     # inicio de B: columna 5 → x=40
    assert p[0][1] != p[-1][1]   # baja de fila


def test_ss_conecta_los_dos_arranques():
    p = puntos(flecha("SS", Extremo(3, 8, 0), Extremo(3, 6, 1), 10, 30, 40))
    assert p[0] == (20, 55)      # inicio de A
    assert p[-1] == (20, 85)     # inicio de B
    assert p[1][0] < p[0][0]     # sale hacia la izquierda


def test_ff_conecta_los_dos_finales():
    p = puntos(flecha("FF", Extremo(1, 9, 0), Extremo(5, 9, 1), 10, 30, 40))
    assert p[0] == (80, 55)
    assert p[-1] == (80, 85)


def test_un_solape_rodea_por_abajo_en_vez_de_cruzar():
    """Si la sucesora arranca antes de que termine la otra, la línea no cruza barras."""
    directa = puntos(flecha("FS", Extremo(1, 10, 0), Extremo(12, 14, 1), 10, 30, 40))
    rodeando = puntos(flecha("FS", Extremo(1, 10, 0), Extremo(3, 6, 1), 10, 30, 40))
    assert len(directa) == 4
    assert len(rodeando) == 6    # dos codos más


def test_la_flecha_baja_a_la_fila_correcta():
    p = puntos(flecha("FS", Extremo(1, 3, 0), Extremo(4, 6, 5), 10, 30, 40))
    assert p[-1][1] == 40 + 5 * 30 + 15
