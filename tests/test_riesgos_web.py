"""El panel de riesgos por HTTP: el formulario, no el service.

Existe por la misma razón que `tests/navegador`: la lógica puede estar bien y el
control no hacer nada. Acá se manda exactamente lo que manda el navegador —todos los
campos del formulario, incluidos los vacíos— y se comprueba qué quedó guardado.
"""

from datetime import date, timedelta

from app.models import Respuesta


def crear_proyecto(cliente, nombre="Obra"):
    return cliente.post(
        "/proyectos",
        data={"nombre": nombre, "descripcion": "", "fecha_inicio": "2026-01-05"},
        follow_redirects=True,
    )


def campos(**cambios) -> dict:
    """Lo que manda el navegador al guardar una fila del registro."""
    datos = {
        "descripcion": "Cae el proveedor", "probabilidad": "5", "impacto": "4",
        "mitigacion": "", "responsable": "", "estado": "abierto",
        "respuesta": "sin_definir", "probabilidad_residual": "",
        "impacto_residual": "", "disparador": "", "revisar_el": "",
        "mitigacion_task_id": "",
    }
    datos.update(cambios)
    return datos


def alta(cliente, **cambios):
    return cliente.post("/proyectos/1/riesgos", data=campos(**cambios))


def panel(cliente) -> str:
    return cliente.get("/proyectos/1/riesgos").text


def test_el_panel_abre_sin_riesgos(cliente):
    crear_proyecto(cliente)
    assert "Todavía no hay riesgos" in panel(cliente)


def test_guardar_una_fila_completa_guarda_todo(cliente):
    crear_proyecto(cliente)
    cliente.post("/proyectos/1/pegar", data={"texto": "Buscar segundo proveedor   5"})
    alta(cliente)

    cliente.post("/proyectos/1/riesgos/1", data=campos(
        respuesta="mitigar", mitigacion="Segundo proveedor en paralelo",
        probabilidad_residual="2", impacto_residual="2",
        disparador="No confirma la fecha de entrega", revisar_el="2026-09-30",
        responsable="Ariel", mitigacion_task_id="1",
    ))

    html = panel(cliente)
    assert "Segundo proveedor en paralelo" in html
    assert "No confirma la fecha de entrega" in html
    assert 'value="2026-09-30"' in html
    assert "Ariel" in html


def test_el_residual_vacio_no_es_cero(cliente):
    """Vacío significa «todavía no se estimó»; el riesgo se dibuja donde está."""
    crear_proyecto(cliente)
    alta(cliente)

    html = panel(cliente)
    assert "20 → <b>20</b>" in html.replace("\n", " ").replace("  ", " ")


def test_el_residual_declarado_baja_la_severidad(cliente):
    crear_proyecto(cliente)
    alta(cliente)
    cliente.post("/proyectos/1/riesgos/1", data=campos(
        respuesta="mitigar", mitigacion="Plan", probabilidad_residual="2",
        impacto_residual="2",
    ))

    assert "20 → <b>4</b>" in panel(cliente).replace("\n", " ").replace("  ", " ")


def test_una_fecha_de_revision_invalida_avisa_y_no_rompe(cliente):
    crear_proyecto(cliente)
    alta(cliente)

    respuesta = cliente.post(
        "/proyectos/1/riesgos/1", data=campos(revisar_el="no-es-fecha"),
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert "no es válida" in respuesta.text
    assert "Traceback" not in respuesta.text


def test_el_registro_avisa_lo_que_falta(cliente):
    crear_proyecto(cliente)
    alta(cliente)

    html = panel(cliente)
    assert "Pendientes del registro" in html
    assert "sin definir qué se va a hacer con ellos" in html


def test_una_revision_vencida_se_marca(cliente):
    crear_proyecto(cliente)
    alta(cliente)
    ayer = (date.today() - timedelta(days=1)).isoformat()
    cliente.post("/proyectos/1/riesgos/1", data=campos(revisar_el=ayer))

    html = panel(cliente)
    assert "con la fecha de revisión vencida" in html
    assert "revision vencida" in html  # la clase CSS de la celda


def test_un_riesgo_bien_cargado_no_deja_pendientes(cliente):
    crear_proyecto(cliente)
    alta(cliente)
    cliente.post("/proyectos/1/riesgos/1", data=campos(
        respuesta="mitigar", mitigacion="Segundo proveedor",
        probabilidad_residual="2", impacto_residual="2",
        disparador="No confirma la fecha", revisar_el="2027-01-15",
    ))

    assert "Pendientes del registro" not in panel(cliente)


def test_los_dos_cuadrantes_se_dibujan(cliente):
    crear_proyecto(cliente)
    alta(cliente)

    html = panel(cliente)
    assert "Inherente" in html and "Residual" in html
    assert html.count("celda-riesgo") == 50  # 25 casillas por cuadrante


def test_la_respuesta_elegida_queda_seleccionada(cliente):
    """El desplegable tiene que volver con lo que se eligió, no con el default."""
    crear_proyecto(cliente)
    alta(cliente)
    cliente.post("/proyectos/1/riesgos/1", data=campos(
        respuesta="transferir", mitigacion="Seguro de caución"))

    html = panel(cliente)
    assert f'value="{Respuesta.transferir.value}" selected' in html


def test_el_plan_solo_apunta_a_tareas_del_proyecto(cliente):
    crear_proyecto(cliente)
    crear_proyecto(cliente, "Otro")
    cliente.post("/proyectos/2/pegar", data={"texto": "Ajena   3"})
    alta(cliente)

    respuesta = cliente.post(
        "/proyectos/1/riesgos/1", data=campos(mitigacion_task_id="1"),
        follow_redirects=True,
    )

    assert "no es de este proyecto" in respuesta.text
