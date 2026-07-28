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
