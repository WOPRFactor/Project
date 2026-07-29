"""Tests de las rutas: usan una DB temporal, nunca la del usuario."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db import get_session
from app.main import app


@pytest.fixture(name="cliente")
def cliente_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def sesion_de_prueba():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sesion_de_prueba
    with TestClient(app) as cliente:
        yield cliente
    app.dependency_overrides.clear()


def test_salud(cliente):
    respuesta = cliente.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok"}


def test_home_sin_proyectos(cliente):
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "Todavía no hay proyectos" in respuesta.text


def crear_proyecto(cliente, nombre="Mudanza", inicio="2026-01-05"):
    return cliente.post(
        "/proyectos",
        data={"nombre": nombre, "descripcion": "", "fecha_inicio": inicio},
        follow_redirects=True,
    )


def celda(cliente, task_id, **campos):
    """Guarda una fila de la grilla como lo hace el navegador."""
    datos = {
        "codigo": "", "titulo": "Tarea", "responsable": "",
        "predecesoras": "", "duracion": "1", "inicio": "",
    }
    datos.update({k: str(v) for k, v in campos.items()})
    return cliente.post(f"/proyectos/1/tareas/{task_id}/celda", data=datos)


def test_alta_de_proyecto_y_tarea(cliente):
    alta = crear_proyecto(cliente)
    assert alta.status_code == 200 and "Mudanza" in alta.text

    assert cliente.post("/proyectos/1/tareas/agregar").status_code == 200
    respuesta = celda(cliente, 1, codigo="1", titulo="Buscar depto", duracion=3)
    assert respuesta.status_code == 200
    assert "Buscar depto" in respuesta.text
    assert "05/01/2026" in respuesta.text


def test_las_dependencias_se_escriben_por_codigo(cliente):
    crear_proyecto(cliente, "Obra")
    for _ in range(2):
        cliente.post("/proyectos/1/tareas/agregar")
    celda(cliente, 1, codigo="1", titulo="A", duracion=3)
    respuesta = celda(cliente, 2, codigo="2", titulo="B", duracion=2, predecesoras="1")

    assert respuesta.status_code == 200
    # B arranca el día hábil siguiente al fin de A (05/01 + 3 días = 07/01)
    assert "08/01/2026" in respuesta.text


def test_una_dependencia_circular_avisa_y_no_rompe(cliente):
    crear_proyecto(cliente, "Obra")
    for _ in range(2):
        cliente.post("/proyectos/1/tareas/agregar")
    celda(cliente, 1, codigo="1", titulo="A", duracion=2)
    celda(cliente, 2, codigo="2", titulo="B", duracion=2, predecesoras="1")
    respuesta = celda(cliente, 1, codigo="1", titulo="A", duracion=2, predecesoras="2")

    assert respuesta.status_code == 200
    assert "ciclo" in respuesta.text.lower()
    assert "Traceback" not in respuesta.text


def test_un_codigo_inexistente_avisa(cliente):
    crear_proyecto(cliente, "Obra")
    cliente.post("/proyectos/1/tareas/agregar")
    respuesta = celda(cliente, 1, codigo="1", titulo="A", predecesoras="9.9")
    assert "No existe ninguna tarea con código 9.9" in respuesta.text


def test_indentar_y_desindentar(cliente):
    crear_proyecto(cliente, "Obra")
    for _ in range(2):
        cliente.post("/proyectos/1/tareas/agregar")
    celda(cliente, 1, codigo="1", titulo="Padre", duracion=2)
    celda(cliente, 2, codigo="2", titulo="Hija", duracion=3)

    indentada = cliente.post("/proyectos/1/tareas/2/indentar")
    assert indentada.status_code == 200
    # el padre pasa a ser resumen: su duración deja de mostrarse
    assert "Padre" in indentada.text

    vuelta = cliente.post("/proyectos/1/tareas/2/desindentar")
    assert vuelta.status_code == 200
    assert "Hija" in vuelta.text


def test_indentar_la_primera_fila_avisa_sin_romper(cliente):
    crear_proyecto(cliente, "Obra")
    cliente.post("/proyectos/1/tareas/agregar")
    respuesta = cliente.post("/proyectos/1/tareas/1/indentar")
    assert respuesta.status_code == 200
    assert "No hay una tarea arriba" in respuesta.text


def subir_planilla(cliente, project_id=1):
    """Sube la planilla real y devuelve la previsualización (todavía no escribe nada)."""
    from pathlib import Path

    planilla = (Path(__file__).parent / "fixtures" / "gantt-traspaso.xlsx").read_bytes()
    return cliente.post(
        f"/proyectos/{project_id}/importar",
        files={"archivo": ("plan.xlsx", planilla, "application/vnd.ms-excel")},
    )


def confirmar_planilla(cliente, previsualizacion, project_id=1, corregir=""):
    import re

    carga = re.search(r'name="carga" value="(.*?)">', previsualizacion.text, re.S).group(1)
    from html import unescape

    return cliente.post(
        f"/proyectos/{project_id}/importar/confirmar",
        data={"carga": unescape(carga), "corregir": corregir},
    )


def test_importar_al_proyecto_previsualiza_antes_de_escribir(cliente):
    """El mismo archivo por los dos caminos tiene que dar el mismo resultado: este
    camino también diagnostica en vez de importar en crudo."""
    crear_proyecto(cliente, "Obra", inicio="2026-08-03")
    previa = subir_planilla(cliente)

    assert previa.status_code == 200
    assert "Previsualización" in previa.text
    assert "no coinciden con sus dependencias" in previa.text
    # todavía no se creó nada
    assert "Etapa 1 — Conformación del Equipo" not in cliente.get("/proyectos/1").text


def test_confirmar_la_previsualizacion_crea_las_tareas(cliente):
    crear_proyecto(cliente, "Obra", inicio="2026-08-03")
    respuesta = confirmar_planilla(cliente, subir_planilla(cliente))

    assert respuesta.status_code == 200
    assert "Etapa 1 — Conformación del Equipo" in respuesta.text
    # las dependencias de la planilla llegaron: 1.3 depende de 1.2
    assert 'value="1.2"' in respuesta.text


def test_el_camino_de_adentro_tambien_corrige_las_relaciones(cliente):
    crear_proyecto(cliente, "Obra", inicio="2026-08-03")
    respuesta = confirmar_planilla(cliente, subir_planilla(cliente), corregir="1")

    assert "dependencias corregidas" in respuesta.text
    # las tres tareas en paralelo entraron como Inicio→Inicio, no Fin→Inicio
    assert "SS" in respuesta.text


def test_cancelar_la_previsualizacion_no_crea_nada(cliente):
    crear_proyecto(cliente, "Obra", inicio="2026-08-03")
    subir_planilla(cliente)
    respuesta = cliente.get("/proyectos/1/tablero")

    assert respuesta.status_code == 200
    assert "Etapa 1 — Conformación del Equipo" not in respuesta.text


def test_importar_al_proyecto_rechaza_lo_que_no_es_planilla(cliente):
    crear_proyecto(cliente, "Obra")
    respuesta = cliente.post(
        "/proyectos/1/importar",
        files={"archivo": ("nota.txt", b"hola", "text/plain")},
    )
    assert respuesta.status_code == 200
    assert ".xlsx" in respuesta.text
    assert "Traceback" not in respuesta.text


def test_importar_dos_veces_avisa_de_los_codigos_repetidos(cliente):
    crear_proyecto(cliente, "Obra", inicio="2026-08-03")
    confirmar_planilla(cliente, subir_planilla(cliente))
    respuesta = confirmar_planilla(cliente, subir_planilla(cliente))

    assert respuesta.status_code == 200
    assert "ya estaba usado" in respuesta.text


def test_pegar_una_lista_en_un_proyecto_existente(cliente):
    crear_proyecto(cliente, "Obra")
    respuesta = cliente.post(
        "/proyectos/1/pegar",
        data={"texto": "Etapa 1\n    Definir alcance   5\n    Relevamiento   10"},
    )
    assert respuesta.status_code == 200
    assert "Definir alcance" in respuesta.text
    assert "Relevamiento" in respuesta.text


def test_export_json_se_descarga(cliente):
    cliente.post(
        "/proyectos",
        data={"nombre": "Obra Norte", "descripcion": "", "fecha_inicio": "2026-01-05"},
    )
    cliente.post("/proyectos/1/tareas/agregar")
    celda(cliente, 1, codigo="1", titulo="Excavación", duracion=3)
    respuesta = cliente.get("/proyectos/1/export/json")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-disposition"] == 'attachment; filename="obra-norte.json"'
    assert respuesta.json()["tareas"][0]["inicio"] == "2026-01-05"


def test_export_markdown_se_descarga(cliente):
    cliente.post(
        "/proyectos",
        data={"nombre": "Obra Sur", "descripcion": "", "fecha_inicio": "2026-01-05"},
    )
    respuesta = cliente.get("/proyectos/1/export/markdown")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-disposition"] == 'attachment; filename="obra-sur.md"'
    assert respuesta.text.startswith("# Obra Sur")


def test_export_de_proyecto_inexistente_da_404(cliente):
    assert cliente.get("/proyectos/999/export/json").status_code == 404
    assert cliente.get("/proyectos/999/export/markdown").status_code == 404


def test_import_de_texto_previsualiza_sin_crear_nada(cliente):
    respuesta = cliente.post(
        "/importar/texto", data={"texto": "Fase\n  Tarea A  3\n  Hito: listo"}
    )
    assert respuesta.status_code == 200
    assert "Se van a crear" in respuesta.text
    assert cliente.get("/").text.count("lista-proyectos") == 0  # nada creado todavía


def test_import_rechaza_un_archivo_que_no_es_planilla(cliente):
    respuesta = cliente.post(
        "/importar/planilla",
        files={"archivo": ("virus.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert respuesta.status_code == 400
    assert ".xlsx" in respuesta.text
    assert "Traceback" not in respuesta.text


def test_import_de_planilla_corrupta_avisa_sin_romper(cliente):
    respuesta = cliente.post(
        "/importar/planilla",
        files={"archivo": ("rota.xlsx", b"no soy una planilla", "application/vnd.ms-excel")},
    )
    assert respuesta.status_code == 400
    assert "No pude leer la planilla" in respuesta.text
    assert "Traceback" not in respuesta.text


def test_confirmar_sin_previsualizacion_no_rompe(cliente):
    respuesta = cliente.post(
        "/importar/confirmar",
        data={"nombre": "X", "fecha_inicio": "2026-01-05", "carga": "basura"},
    )
    assert respuesta.status_code == 400
    assert "Traceback" not in respuesta.text


def test_proyecto_inexistente_da_404_sin_stack_trace(cliente):
    respuesta = cliente.get("/proyectos/999")
    assert respuesta.status_code == 404
    assert "Traceback" not in respuesta.text


def test_duracion_invalida_no_rompe_la_grilla(cliente):
    crear_proyecto(cliente, "Test")
    cliente.post("/proyectos/1/tareas/agregar")
    respuesta = celda(cliente, 1, titulo="Rara", duracion=-5)
    assert respuesta.status_code == 200
    assert "Traceback" not in respuesta.text


def test_duracion_cero_crea_un_hito(cliente):
    crear_proyecto(cliente, "Test")
    cliente.post("/proyectos/1/tareas/agregar")
    respuesta = celda(cliente, 1, codigo="1", titulo="Firma del acta", duracion=0)
    assert respuesta.status_code == 200
    assert "Hito" in respuesta.text or "◆" in respuesta.text


def test_titulo_vacio_no_rompe_la_grilla(cliente):
    crear_proyecto(cliente, "Test")
    cliente.post("/proyectos/1/tareas/agregar")
    respuesta = celda(cliente, 1, titulo="   ")
    assert respuesta.status_code == 200
    assert "Traceback" not in respuesta.text


def test_mover_el_arranque_recalcula_todo(cliente):
    crear_proyecto(cliente, "Obra", inicio="2026-01-05")
    for _ in range(2):
        cliente.post("/proyectos/1/tareas/agregar")
    celda(cliente, 1, codigo="1", titulo="A", duracion=3)
    respuesta = celda(cliente, 2, codigo="2", titulo="B", duracion=2, predecesoras="1")
    assert "08/01/2026" in respuesta.text   # B arranca tras A

    # se mueve el arranque un mes: todo el encadenado se corre
    movido = cliente.post("/proyectos/1/inicio", data={"fecha_inicio": "2026-02-02"})
    assert movido.status_code == 200
    assert "02/02/2026" in movido.text     # A
    assert "05/02/2026" in movido.text     # B, tres días hábiles después
    assert "08/01/2026" not in movido.text
    assert "Arranque movido" in movido.text


def test_mover_el_arranque_a_un_fin_de_semana_corre_al_lunes(cliente):
    crear_proyecto(cliente, "Obra", inicio="2026-01-05")
    cliente.post("/proyectos/1/tareas/agregar")
    celda(cliente, 1, codigo="1", titulo="A", duracion=1)
    movido = cliente.post("/proyectos/1/inicio", data={"fecha_inicio": "2026-02-07"})
    assert "09/02/2026" in movido.text     # sábado 07 → lunes 09


def test_una_fecha_de_arranque_invalida_no_rompe(cliente):
    crear_proyecto(cliente, "Obra")
    cliente.post("/proyectos/1/tareas/agregar")
    respuesta = cliente.post("/proyectos/1/inicio", data={"fecha_inicio": "no-es-fecha"})
    assert respuesta.status_code == 200
    assert "no es válida" in respuesta.text
    assert "Traceback" not in respuesta.text


# --- columnas de la grilla ---
# El Gantt había desaparecido de la pantalla: la grilla creció a catorce columnas y
# empujó la pista del timeline fuera del ancho útil. El ancho se arregla en CSS, pero
# lo que evita que vuelva a pasar es poder apagar columnas — y eso sí se testea.

def test_la_grilla_muestra_solo_las_columnas_elegidas(cliente):
    crear_proyecto(cliente, "Obra")
    cliente.post("/proyectos/1/pegar", data={"texto": "Relevamiento   5"})

    respuesta = cliente.get("/proyectos/1?columnas=dias&columnas=fin")

    assert 'name="duracion"' in respuesta.text
    assert 'name="responsable"' not in respuesta.text
    assert 'name="peso"' not in respuesta.text


def test_por_defecto_no_se_muestran_todas(cliente):
    crear_proyecto(cliente, "Obra")
    cliente.post("/proyectos/1/pegar", data={"texto": "Relevamiento   5"})

    respuesta = cliente.get("/proyectos/1")

    assert 'name="responsable"' in respuesta.text   # una de las de por defecto
    assert 'name="peso"' not in respuesta.text      # una de las opcionales


def test_la_eleccion_de_columnas_sobrevive_a_una_edicion(cliente):
    crear_proyecto(cliente, "Obra")
    cliente.post("/proyectos/1/pegar", data={"texto": "Relevamiento   5"})

    respuesta = cliente.post(
        "/proyectos/1/tareas/1/celda",
        data={"codigo": "1", "titulo": "Relevamiento", "duracion": "5",
              "columnas": "dias,fin"},
    )

    assert 'name="duracion"' in respuesta.text
    assert 'name="responsable"' not in respuesta.text


# --- flechas de dependencia ---
# Un checkbox sin tildar no viaja en el request. Si el servidor tomara "no vino" como
# "no la tocó", apagar las flechas sería imposible desde la pantalla: por eso el
# formulario manda además un campo oculto en 0 y acá se prueban las tres formas.

def _proyecto_encadenado(cliente):
    crear_proyecto(cliente, "Obra")
    cliente.post("/proyectos/1/pegar", data={"texto": "Relevamiento   5\nAnalisis   3"})
    cliente.post(
        "/proyectos/1/tareas/2/celda",
        data={"codigo": "2", "titulo": "Analisis", "duracion": "3", "predecesoras": "1"},
    )


def test_las_flechas_se_dibujan_por_defecto(cliente):
    _proyecto_encadenado(cliente)

    assert 'class="conexion' in cliente.get("/proyectos/1").text


def test_el_oculto_en_cero_apaga_las_flechas(cliente):
    _proyecto_encadenado(cliente)

    # Lo que manda el formulario con el interruptor destildado.
    assert 'class="conexion' not in cliente.get("/proyectos/1?flechas=0").text


def test_tildado_manda_el_oculto_y_el_checkbox(cliente):
    _proyecto_encadenado(cliente)

    # Prendido viajan los dos campos; alcanza con que uno venga prendido.
    assert 'class="conexion' in cliente.get("/proyectos/1?flechas=0&flechas=1").text


def test_apagadas_sobreviven_a_una_edicion(cliente):
    _proyecto_encadenado(cliente)

    respuesta = cliente.post(
        "/proyectos/1/tareas/1/celda",
        data={"codigo": "1", "titulo": "Relevamiento", "duracion": "6", "flechas": "0"},
    )

    assert 'class="conexion' not in respuesta.text
