"""La grilla manejada con clics de verdad: lo que los tests de server no ven.

Son los casos que en julio 2026 se verificaron a mano — y donde vivió el bug 3
de PENDIENTES: la lógica estaba bien y con tests, lo roto era el control.
"""

from __future__ import annotations


def test_la_barra_de_vista_aplica_de_verdad(pagina):
    """El bug 3: un hx-vals heredado pisaba los controles y ninguno hacía nada."""
    pagina.goto(f"{pagina.base}/proyectos/1?detalle=todo&colapsadas=")
    pagina.wait_for_selector(".fila")
    total = pagina.locator(".fila").count()

    pagina.select_option("select[name='color']", "estado")
    pagina.wait_for_timeout(700)
    assert pagina.eval_on_selector("select[name='color']", "e => e.value") == "estado"

    pagina.select_option("select[name='detalle']", "etapas")
    pagina.wait_for_timeout(700)
    assert pagina.locator(".fila").count() < total
    assert pagina.errores == []


def test_el_chevron_pliega_y_la_vista_persiste(pagina):
    pagina.goto(f"{pagina.base}/proyectos/1?detalle=todo&colapsadas=")
    pagina.wait_for_selector(".chevron")
    antes = pagina.locator(".fila").count()

    pagina.locator(".chevron").first.click()
    pagina.wait_for_timeout(700)
    plegadas = pagina.locator(".fila").count()
    assert plegadas < antes

    # Salir y volver con un link pelado retoma la vista tal como quedó.
    pagina.goto(f"{pagina.base}/proyectos/1/equipo")
    pagina.goto(f"{pagina.base}/proyectos/1")
    pagina.wait_for_selector(".fila")
    assert pagina.locator(".fila").count() == plegadas

    pagina.locator(".chevron").first.click()  # dejarla desplegada para el resto
    pagina.wait_for_timeout(700)
    assert pagina.errores == []


def test_borrar_una_fila_no_salta_el_scroll(pagina):
    pagina.goto(f"{pagina.base}/proyectos/1?detalle=todo&colapsadas=")
    pagina.wait_for_selector(".fila")
    filas = pagina.locator(".fila").count()
    pagina.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    pagina.wait_for_timeout(200)
    antes = pagina.evaluate("window.scrollY")

    pagina.locator(".fila .c-ops button[title='Borrar']").last.click()
    pagina.wait_for_timeout(900)
    assert pagina.locator(".fila").count() == filas - 1
    assert abs(pagina.evaluate("window.scrollY") - antes) < 60
    assert pagina.errores == []


def test_editar_conserva_el_scroll_del_timeline(pagina):
    pagina.goto(f"{pagina.base}/proyectos/1")
    pagina.wait_for_selector(".fila")
    pagina.evaluate("document.querySelector('.gantt').scrollLeft = 400")
    pagina.wait_for_timeout(150)

    titulo = pagina.locator(".fila input[name='titulo']").first
    titulo.fill("Título editado desde el test")
    titulo.press("Tab")
    pagina.wait_for_timeout(900)
    assert abs(pagina.evaluate("document.querySelector('.gantt').scrollLeft") - 400) < 40
    assert pagina.errores == []


def test_las_cabeceras_quedan_a_la_vista_al_bajar(pagina):
    pagina.goto(f"{pagina.base}/proyectos/1?detalle=todo&colapsadas=")
    pagina.wait_for_selector(".fila")
    pagina.evaluate("window.scrollTo(0, 700)")
    pagina.wait_for_timeout(300)
    tops = pagina.evaluate(
        "[document.querySelector('.panel-izq .cabecera').getBoundingClientRect().top,"
        " document.querySelector('.cabecera-grilla').getBoundingClientRect().top]"
    )
    assert all(-5 <= t <= 120 for t in tops)
    assert pagina.errores == []


def test_aplicar_del_asistente_solo_escribe_con_confirmacion(pagina):
    """El flujo de confirmación de la fase 29b contra el server real. La parte de
    proponer necesita a Groq (no determinista); acá se ejercita el aplicar."""
    pagina.goto(f"{pagina.base}/proyectos/1?detalle=todo&colapsadas=")
    pagina.wait_for_selector(".fila")
    assert pagina.locator("button[data-alterna='asistente-bloque']").count() == 1
    antes = pagina.locator(".fila").count()

    carga = (
        '[{"tipo": "crear_tarea", "titulo": "Confirmada en navegador",'
        ' "padre_wbs": "", "duracion": 2, "predecesoras": "", "critica": false}]'
    )
    # El token CSRF que la app expone en el <meta>, igual que hace grilla.js.
    token = pagina.eval_on_selector("meta[name='csrf-token']", "e => e.content")
    respuesta = pagina.request.post(
        f"{pagina.base}/proyectos/1/asistente/aplicar",
        form={"carga": carga},
        headers={"X-CSRF-Token": token},
    )
    assert respuesta.status == 200

    pagina.goto(f"{pagina.base}/proyectos/1?detalle=todo&colapsadas=")
    pagina.wait_for_selector(".fila")
    assert pagina.locator(".fila").count() == antes + 1
    assert pagina.errores == []


def test_el_conflicto_de_edicion_se_ve_en_pantalla(pagina):
    """Fase 12. Un 409 no lo pinta HTMX por default: sin el `htmx:beforeSwap` de
    `grilla.js`, el guardado se rechazaría **en silencio** y la pantalla quedaría
    mostrando lo que el usuario escribió como si se hubiera guardado."""
    pagina.goto(f"{pagina.base}/proyectos/1?detalle=todo&colapsadas=")
    pagina.wait_for_selector(".fila")

    fila = pagina.locator(".fila").first
    titulo_real = fila.locator("input[name='titulo']").input_value()
    # Una pantalla atrasada es exactamente esto: la versión que manda no es la actual.
    fila.locator("input[name='version']").evaluate("e => e.value = '99999'")
    fila.locator("input[name='titulo']").fill("Pisado por el que llegó tarde")
    fila.locator("input[name='titulo']").dispatch_event("change")
    pagina.wait_for_timeout(900)

    assert "Alguien editó esta fila" in pagina.locator("#tablero").inner_text()
    # Y la grilla volvió a mostrar el valor real, no lo que se quiso escribir.
    assert (
        pagina.locator(".fila").first.locator("input[name='titulo']").input_value()
        == titulo_real
    )
    # El 409 es el resultado esperado acá; cualquier otro error no.
    assert [e for e in pagina.errores if "409" not in e] == []


def test_todas_las_paginas_y_exports_responden_sin_errores(pagina):
    paginas = [
        "/", "/proyectos/1", "/proyectos/1/equipo", "/proyectos/1/estados",
        "/proyectos/1/riesgos", "/proyectos/1/base", "/proyectos/1/informe",
        "/proyectos/1/historial", "/proyectos/1/miembros",
        "/importar", "/proyectos/nuevo", "/proyectos/1/editar",
    ]
    for ruta in paginas:
        respuesta = pagina.goto(f"{pagina.base}{ruta}")
        assert respuesta.status == 200, ruta

    exports = [
        "/proyectos/1/export/excel", "/proyectos/1/export/markdown",
        "/proyectos/1/export/json", "/importar/plantilla",
    ]
    for export in exports:
        assert pagina.request.get(f"{pagina.base}{export}").status == 200, export
    assert pagina.errores == []
