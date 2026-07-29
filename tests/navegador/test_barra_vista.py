"""Los controles de la barra de vista, tocados como los toca una persona.

Cada test de acá corresponde a un bug real que la suite sin navegador no vio: la
lógica pasaba, el control no hacía nada. Por eso las aserciones miran el **efecto en
pantalla**, no el request ni el estado del servidor.
"""

import pytest

pytestmark = pytest.mark.navegador


def filas(pagina) -> int:
    return pagina.eval_on_selector_all(".panel-izq .fila", "e => e.length")


def test_cambiar_el_detalle_filtra_las_filas(pagina, proyecto_cargado):
    pagina.goto(proyecto_cargado, wait_until="networkidle")
    assert filas(pagina) == 6

    pagina.select_option('select[name="detalle"]', "etapas")
    pagina.wait_for_timeout(600)

    # quedan las dos etapas y el hito
    assert filas(pagina) == 3
    assert pagina.input_value('select[name="detalle"]') == "etapas"


def test_filtrar_por_etapa_deja_solo_esa_rama(pagina, proyecto_cargado):
    pagina.goto(proyecto_cargado, wait_until="networkidle")
    valor = pagina.eval_on_selector(
        'select[name="etapa"] option:nth-child(2)', "e => e.value"
    )

    pagina.select_option('select[name="etapa"]', valor)
    pagina.wait_for_timeout(600)

    assert filas(pagina) == 3  # Etapa 1 + sus dos hijas
    assert "siguen siendo del proyecto entero" in pagina.inner_text(".barra-vista")


def test_cambiar_el_modo_de_color_repinta_las_barras(pagina, proyecto_cargado):
    pagina.goto(proyecto_cargado, wait_until="networkidle")

    pagina.select_option('select[name="color"]', "estado")
    pagina.wait_for_timeout(600)

    assert pagina.input_value('select[name="color"]') == "estado"
    assert pagina.eval_on_selector_all(".barra-tarea.color-gris", "e => e.length") > 0


def test_prender_una_columna_la_muestra(pagina, proyecto_cargado):
    """El bug que reportó Ariel: tildar una columna no hacía nada."""
    pagina.goto(proyecto_cargado, wait_until="networkidle")
    assert pagina.query_selector(".cabecera .c-peso") is None

    pagina.click(".columnas-menu summary")
    pagina.check('.columnas-lista input[value="peso"]')
    pagina.wait_for_timeout(600)

    assert pagina.query_selector(".cabecera .c-peso") is not None
    assert pagina.is_checked('.columnas-lista input[value="peso"]')


def test_apagar_una_columna_la_esconde(pagina, proyecto_cargado):
    pagina.goto(proyecto_cargado, wait_until="networkidle")
    assert pagina.query_selector(".cabecera .c-resp") is not None

    pagina.click(".columnas-menu summary")
    pagina.uncheck('.columnas-lista input[value="resp"]')
    pagina.wait_for_timeout(600)

    assert pagina.query_selector(".cabecera .c-resp") is None


def test_apagar_las_flechas_las_saca_del_gantt(pagina, proyecto_cargado):
    pagina.goto(proyecto_cargado, wait_until="networkidle")

    assert pagina.eval_on_selector_all(".conexion", "e => e.length") > 0

    # El `name` lo comparten con el campo oculto que hace posible mandar "apagadas".
    interruptor = 'input[type="checkbox"][name="flechas"]'
    pagina.uncheck(interruptor)
    pagina.wait_for_timeout(600)

    assert pagina.eval_on_selector_all(".conexion", "e => e.length") == 0
    assert not pagina.is_checked(interruptor)


def test_la_vista_elegida_sobrevive_a_editar_una_celda(pagina, proyecto_cargado):
    """Es lo que el `hx-vals` protege; el arreglo del bug no podía romperlo."""
    pagina.goto(proyecto_cargado, wait_until="networkidle")
    pagina.select_option('select[name="color"]', "ambito")
    pagina.wait_for_timeout(600)

    campo = pagina.query_selector('.fila input[name="duracion"]')
    campo.fill("12")
    pagina.keyboard.press("Tab")
    pagina.wait_for_timeout(800)

    assert pagina.input_value('select[name="color"]') == "ambito"
