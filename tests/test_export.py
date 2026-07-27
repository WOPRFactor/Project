import json
from datetime import date

from sqlmodel import Session

from app.models import EstadoTarea, Project
from app.schemas import DependenciaIn, TareaIn
from app.services import dependencies as dependencies_service
from app.services import export as export_service
from app.services import tasks as tasks_service


def armar_proyecto(session: Session, proyecto):
    padre = tasks_service.crear(session, proyecto.id, TareaIn(titulo="Relevamiento"))
    a = tasks_service.crear(
        session, proyecto.id, TareaIn(titulo="Entrevistas", duracion=3, parent_id=padre.id)
    )
    b = tasks_service.crear(
        session, proyecto.id, TareaIn(titulo="Informe", duracion=2, parent_id=padre.id)
    )
    dependencies_service.crear(
        session, proyecto.id, DependenciaIn(predecessor_id=a.id, successor_id=b.id, lag=2)
    )
    return padre, a, b


def test_json_incluye_estructura_fechas_y_dependencias(session: Session, proyecto):
    padre, a, b = armar_proyecto(session, proyecto)
    datos = export_service.a_json(session, proyecto.id)

    assert datos["proyecto"]["nombre"] == "Proyecto de prueba"
    assert datos["error_de_calculo"] is None

    por_titulo = {t["titulo"]: t for t in datos["tareas"]}
    assert por_titulo["Entrevistas"]["inicio"] == "2026-01-05"
    assert por_titulo["Entrevistas"]["fin"] == "2026-01-07"
    assert por_titulo["Informe"]["inicio"] == "2026-01-12"
    assert por_titulo["Relevamiento"]["es_resumen"] is True
    assert por_titulo["Relevamiento"]["duracion_dias_habiles"] is None
    assert por_titulo["Entrevistas"]["nivel"] == 1

    assert datos["dependencias"] == [
        {
            "predecesora_id": a.id,
            "predecesora": "Entrevistas",
            "sucesora_id": b.id,
            "sucesora": "Informe",
            "lag_dias_habiles": 2,
        }
    ]


def test_json_es_serializable(session: Session, proyecto):
    armar_proyecto(session, proyecto)
    texto = json.dumps(export_service.a_json(session, proyecto.id), ensure_ascii=False)
    assert "Entrevistas" in texto


def test_markdown_arma_el_arbol_con_fechas(session: Session, proyecto):
    armar_proyecto(session, proyecto)
    texto = export_service.a_markdown(session, proyecto.id)

    assert texto.startswith("# Proyecto de prueba")
    assert "- **Inicio del proyecto:** 05/01/2026" in texto
    assert "- **Fin calculado:** 13/01/2026" in texto
    assert "- **Relevamiento**" in texto
    assert "  - Entrevistas — 05/01/2026 → 07/01/2026 · 3d" in texto
    assert "**Informe** arranca cuando termina **Entrevistas**, más 2 días hábiles" in texto


def test_markdown_marca_las_tareas_hechas(session: Session, proyecto):
    _, a, _ = armar_proyecto(session, proyecto)
    tasks_service.cambiar_estado(session, a.id, EstadoTarea.hecha)
    texto = export_service.a_markdown(session, proyecto.id)
    assert "~~Entrevistas~~" in texto


def test_markdown_describe_el_solape(session: Session, proyecto):
    a = tasks_service.crear(session, proyecto.id, TareaIn(titulo="A", duracion=3))
    b = tasks_service.crear(session, proyecto.id, TareaIn(titulo="B", duracion=2))
    dependencies_service.crear(
        session, proyecto.id, DependenciaIn(predecessor_id=a.id, successor_id=b.id, lag=-1)
    )
    texto = export_service.a_markdown(session, proyecto.id)
    assert "con 1 días hábiles de solape" in texto


def test_proyecto_sin_tareas_exporta_igual(session: Session, proyecto):
    assert export_service.a_json(session, proyecto.id)["tareas"] == []
    assert "_Sin tareas cargadas._" in export_service.a_markdown(session, proyecto.id)


def test_proyecto_inexistente_devuelve_none(session: Session):
    assert export_service.a_json(session, 999) is None
    assert export_service.a_markdown(session, 999) is None


def test_el_nombre_de_archivo_se_sanea():
    peligroso = Project(
        nombre='Obra "2026"\r\nX: inyectado', fecha_inicio=date(2026, 1, 5)
    )
    archivo = export_service.nombre_de_archivo(peligroso, "json")
    assert archivo == "obra-2026-x-inyectado.json"
    assert '"' not in archivo and "\r" not in archivo and "\n" not in archivo


def test_el_nombre_de_archivo_translitera_acentos():
    proyecto = Project(nombre="Implementación ISO — Ñandú", fecha_inicio=date(2026, 1, 5))
    assert export_service.nombre_de_archivo(proyecto, "md") == "implementacion-iso-nandu.md"


def test_nombre_sin_alfanumericos_no_queda_vacio():
    assert export_service.nombre_de_archivo(
        Project(nombre="///", fecha_inicio=date(2026, 1, 5)), "md"
    ) == "proyecto.md"
