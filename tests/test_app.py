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


def test_alta_de_proyecto_y_tarea(cliente):
    alta = cliente.post(
        "/proyectos",
        data={"nombre": "Mudanza", "descripcion": "", "fecha_inicio": "2026-01-05"},
        follow_redirects=True,
    )
    assert alta.status_code == 200
    assert "Mudanza" in alta.text

    tarea = cliente.post(
        "/proyectos/1/tareas",
        data={"titulo": "Buscar depto", "duracion": "3", "snet": "", "parent_id": ""},
    )
    assert tarea.status_code == 200
    assert "Buscar depto" in tarea.text
    assert "05/01/2026" in tarea.text


def test_dependencia_circular_muestra_aviso_y_no_rompe(cliente):
    cliente.post(
        "/proyectos",
        data={"nombre": "Obra", "descripcion": "", "fecha_inicio": "2026-01-05"},
    )
    for titulo in ("A", "B"):
        cliente.post(
            "/proyectos/1/tareas",
            data={"titulo": titulo, "duracion": "2", "snet": "", "parent_id": ""},
        )
    cliente.post(
        "/proyectos/1/dependencias",
        data={"predecessor_id": "1", "successor_id": "2", "lag": "0"},
    )
    respuesta = cliente.post(
        "/proyectos/1/dependencias",
        data={"predecessor_id": "2", "successor_id": "1", "lag": "0"},
    )
    assert respuesta.status_code == 200
    assert "ciclo" in respuesta.text.lower()
    assert "Traceback" not in respuesta.text


def test_export_json_se_descarga(cliente):
    cliente.post(
        "/proyectos",
        data={"nombre": "Obra Norte", "descripcion": "", "fecha_inicio": "2026-01-05"},
    )
    cliente.post(
        "/proyectos/1/tareas",
        data={"titulo": "Excavación", "duracion": "3", "snet": "", "parent_id": ""},
    )
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


def test_duracion_invalida_no_rompe_la_vista(cliente):
    cliente.post(
        "/proyectos",
        data={"nombre": "Test", "descripcion": "", "fecha_inicio": "2026-01-05"},
    )
    respuesta = cliente.post(
        "/proyectos/1/tareas",
        data={"titulo": "Rara", "duracion": "0", "snet": "", "parent_id": ""},
    )
    assert respuesta.status_code == 200
    assert "Traceback" not in respuesta.text
