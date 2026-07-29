"""El registro de riesgos, tocado como lo toca una persona.

Lo que se prueba acá y no se puede probar sin navegador: que los controles de la fila
existan y estén enganchados al formulario que se envía. Es una fila con doce campos;
que uno quede afuera del `<form>` no lo ve ninguna prueba de servidor.
"""

import pytest

pytestmark = pytest.mark.navegador


def ir_a_riesgos(pagina, proyecto_cargado):
    pagina.goto(proyecto_cargado, wait_until="networkidle")
    pagina.click('a[href$="/riesgos"]')
    pagina.wait_for_selector("h1")


def test_se_llega_a_riesgos_desde_el_tablero(pagina, proyecto_cargado):
    ir_a_riesgos(pagina, proyecto_cargado)
    assert "Riesgos" in pagina.inner_text("h1")
    assert "Todavía no hay riesgos" in pagina.inner_text("body")


def test_cargar_un_riesgo_lo_ubica_en_los_dos_cuadrantes(pagina, proyecto_cargado):
    ir_a_riesgos(pagina, proyecto_cargado)

    pagina.fill('form.en-fila input[name="descripcion"]', "Cae el proveedor")
    pagina.select_option('form.en-fila select[name="probabilidad"]', "5")
    pagina.select_option('form.en-fila select[name="impacto"]', "4")
    pagina.click('form.en-fila button[type="submit"]')
    pagina.wait_for_selector(".fila-riesgo")

    # Un riesgo, dibujado en las dos matrices mientras no tenga residual estimado.
    assert pagina.eval_on_selector_all(".celda-riesgo.con-riesgos", "e => e.length") == 2


def test_declarar_el_residual_lo_mueve_solo_en_la_matriz_residual(pagina, proyecto_cargado):
    ir_a_riesgos(pagina, proyecto_cargado)
    pagina.fill('form.en-fila input[name="descripcion"]', "Cae el proveedor")
    pagina.select_option('form.en-fila select[name="probabilidad"]', "5")
    pagina.select_option('form.en-fila select[name="impacto"]', "5")
    pagina.click('form.en-fila button[type="submit"]')
    pagina.wait_for_selector(".fila-riesgo")

    pagina.select_option('.fila-riesgo select[name="respuesta"]', "mitigar")
    pagina.fill('.fila-riesgo input[name="mitigacion"]', "Segundo proveedor")
    pagina.select_option('.fila-riesgo select[name="probabilidad_residual"]', "1")
    pagina.select_option('.fila-riesgo select[name="impacto_residual"]', "2")
    pagina.click('.fila-riesgo button[type="submit"]')
    pagina.wait_for_selector(".fila-riesgo")

    zonas = pagina.eval_on_selector_all(
        ".celda-riesgo.con-riesgos", "e => e.map(x => x.className)"
    )
    assert len(zonas) == 2
    assert any("zona-critico" in c for c in zonas)   # inherente: 5×5
    assert any("zona-bajo" in c for c in zonas)      # residual: 1×2

    assert "25 → 2" in pagina.inner_text(".fila-riesgo .sev")


def test_los_pendientes_del_registro_se_ven_y_se_van(pagina, proyecto_cargado):
    ir_a_riesgos(pagina, proyecto_cargado)
    pagina.fill('form.en-fila input[name="descripcion"]', "Cae el proveedor")
    pagina.click('form.en-fila button[type="submit"]')
    pagina.wait_for_selector(".fila-riesgo")

    assert pagina.query_selector(".alertas-riesgo") is not None

    pagina.select_option('.fila-riesgo select[name="respuesta"]', "aceptar")
    pagina.click('.fila-riesgo button[type="submit"]')
    pagina.wait_for_selector(".fila-riesgo")

    assert pagina.query_selector(".alertas-riesgo") is None


def test_el_responsable_del_riesgo_aparece_en_el_equipo(pagina, proyecto_cargado):
    """Lo que hace que valga la pena que sea una persona y no un texto suelto."""
    ir_a_riesgos(pagina, proyecto_cargado)
    pagina.fill('form.en-fila input[name="descripcion"]', "Cae el proveedor")
    pagina.click('form.en-fila button[type="submit"]')
    pagina.wait_for_selector(".fila-riesgo")

    pagina.fill('.fila-riesgo input[name="responsable"]', "Ariel")
    pagina.click('.fila-riesgo button[type="submit"]')
    pagina.wait_for_selector(".fila-riesgo")

    pagina.goto(proyecto_cargado + "/equipo", wait_until="networkidle")
    texto = pagina.inner_text("body")
    assert "Ariel" in texto
    assert "1 riesgos" in texto
