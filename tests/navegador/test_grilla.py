"""Geometría de la grilla: lo que solo se puede comprobar midiendo en pantalla.

El ancho de las columnas es CSS y ninguna prueba de servidor lo ve. Los tres bugs
que dieron origen a estos tests fueron: el timeline aplastado a 90px, los títulos
cortados, y dos barras de scroll horizontales pegadas.
"""

import pytest

pytestmark = pytest.mark.navegador

TODAS = ["resp", "pred", "dias", "rango", "inicio", "fin", "desvio",
         "crit", "peso", "avance", "riesgo", "estado", "ambito"]


def anchos(pagina) -> dict:
    return {
        "grilla": pagina.eval_on_selector(".panel-izq", "e => e.getBoundingClientRect().width"),
        "visible": pagina.eval_on_selector(".gantt", "e => e.clientWidth"),
        "barras": pagina.eval_on_selector_all(
            ".panel-der .barra-tarea",
            "e => e.filter(x => x.getBoundingClientRect().width > 0).length",
        ),
    }


def test_el_timeline_siempre_tiene_lugar(pagina, proyecto_cargado):
    """La grilla llegó a ocupar 1460 de 1550px y dejó la pista en 90."""
    pagina.goto(proyecto_cargado, wait_until="networkidle")
    m = anchos(pagina)
    assert m["visible"] - m["grilla"] > 400
    assert m["barras"] > 0


def test_con_todas_las_columnas_el_gantt_sigue_visible(pagina, proyecto_cargado):
    """Anclada y sin tope, la grilla tapaba el Gantt entero."""
    pagina.goto(proyecto_cargado + "?" + "&".join(f"columnas={c}" for c in TODAS),
                wait_until="networkidle")
    m = anchos(pagina)
    assert m["visible"] - m["grilla"] > 300
    assert m["barras"] > 0


def test_hay_una_sola_barra_de_scroll_horizontal(pagina, proyecto_cargado):
    """Hubo dos pegadas —la de la grilla y la del timeline— y se movía la equivocada."""
    pagina.goto(proyecto_cargado, wait_until="networkidle")
    internos = pagina.eval_on_selector_all(
        ".panel-izq, .panel-der",
        "e => e.filter(x => x.scrollWidth > x.clientWidth).length",
    )
    assert internos == 0
    assert pagina.eval_on_selector(".gantt", "e => e.scrollWidth > e.clientWidth")


def test_la_grilla_queda_anclada_al_desplazarse(pagina, proyecto_cargado):
    pagina.goto(proyecto_cargado, wait_until="networkidle")
    antes = pagina.eval_on_selector(".panel-izq", "e => e.getBoundingClientRect().x")

    pagina.eval_on_selector(".gantt", "e => e.scrollLeft = 600")
    pagina.wait_for_timeout(300)

    despues = pagina.eval_on_selector(".panel-izq", "e => e.getBoundingClientRect().x")
    assert round(antes) == round(despues)


def test_los_encabezados_no_se_van_al_bajar(pagina, proyecto_cargado):
    """Lo que reportó Ariel: al bajar se perdía el nombre de las columnas."""
    pagina.goto(proyecto_cargado, wait_until="networkidle")
    y_columna = pagina.eval_on_selector(".panel-izq .cabecera", "e => e.getBoundingClientRect().y")
    y_semanas = pagina.eval_on_selector(".panel-der .cabecera-grilla", "e => e.getBoundingClientRect().y")

    pagina.eval_on_selector(".gantt", "e => e.scrollTop = e.scrollHeight")
    pagina.wait_for_timeout(300)

    # Un píxel de tolerancia: el redondeo del layout tras el scroll mueve la caja
    # medio píxel y eso no es perder el encabezado, que es lo que se está probando.
    columna = pagina.eval_on_selector(".panel-izq .cabecera", "e => e.getBoundingClientRect().y")
    semanas = pagina.eval_on_selector(".panel-der .cabecera-grilla", "e => e.getBoundingClientRect().y")
    assert abs(columna - y_columna) <= 1
    assert abs(semanas - y_semanas) <= 1


def test_arrastrar_el_borde_cambia_el_ancho_y_queda_guardado(pagina, proyecto_cargado):
    pagina.goto(proyecto_cargado, wait_until="networkidle")
    ancho = lambda: pagina.eval_on_selector(".cabecera .c-tarea", "e => e.getBoundingClientRect().width")
    antes = ancho()

    caja = pagina.query_selector(".cabecera .c-tarea .tirador").bounding_box()
    pagina.mouse.move(caja["x"] + 3, caja["y"] + caja["height"] / 2)
    pagina.mouse.down()
    pagina.mouse.move(caja["x"] + 123, caja["y"] + caja["height"] / 2, steps=10)
    pagina.mouse.up()
    pagina.wait_for_timeout(200)

    assert ancho() > antes + 80
    assert pagina.evaluate("() => Object.keys(JSON.parse(Object.keys(localStorage)"
                           ".filter(k => k.startsWith('wopr.anchos'))"
                           ".map(k => localStorage.getItem(k))[0] || '{}')).length") == 1


def test_los_titulos_largos_no_se_cortan_con_pocas_columnas(pagina, proyecto_cargado):
    """Apagar columnas ensancha la columna Tarea en vez de dejar aire."""
    pagina.goto(proyecto_cargado + "?columnas=dias&columnas=fin", wait_until="networkidle")
    cortados = pagina.evaluate(
        "() => [...document.querySelectorAll('input[name=titulo]')]"
        ".filter(i => i.scrollWidth > i.clientWidth + 1).length"
    )
    assert cortados == 0
