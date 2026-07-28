"""Operaciones de fila de la grilla y códigos WBS."""

from datetime import date

import pytest
from sqlmodel import Session

from app.schemas import TareaIn
from app.services import arbol as arbol_service
from app.services import dependencies as dependencies_service
from app.services import predecesoras as predecesoras_service
from app.services import schedule as schedule_service
from app.services import tasks as tasks_service
from app.services.tasks import TareaInvalida


def agregar(session, proyecto, titulo, duracion=1, parent=None):
    return arbol_service.agregar_al_final(
        session, proyecto.id, TareaIn(titulo=titulo, duracion=duracion, parent_id=parent)
    )


def codigos(session, project_id):
    return [t.codigo for t, _ in tasks_service.arbol(session, project_id)]


def test_los_codigos_se_asignan_por_nivel(session: Session, proyecto):
    a = agregar(session, proyecto, "Uno")
    agregar(session, proyecto, "Dos")
    agregar(session, proyecto, "Uno punto uno", parent=a.id)
    assert codigos(session, proyecto.id) == ["1", "1.1", "2"]


def test_el_codigo_es_unico_en_todo_el_proyecto(session: Session, proyecto):
    """Bajo un padre sin código, el hijo no puede pisar un código de primer nivel."""
    sin_codigo = agregar(session, proyecto, "Sin WBS")
    sin_codigo.codigo = ""
    session.add(sin_codigo)
    session.commit()
    agregar(session, proyecto, "Primero")  # toma "1"

    hija = agregar(session, proyecto, "Hija", parent=sin_codigo.id)
    todos = [c for c in codigos(session, proyecto.id) if c]
    assert hija.codigo != "1"
    assert len(todos) == len(set(todos))


def test_insertar_debajo_respeta_el_orden(session: Session, proyecto):
    primera = agregar(session, proyecto, "Primera")
    agregar(session, proyecto, "Segunda")
    nueva = arbol_service.insertar_debajo(session, primera.id)
    titulos = [t.titulo for t, _ in tasks_service.arbol(session, proyecto.id)]
    assert titulos == ["Primera", nueva.titulo, "Segunda"]


def test_indentar_la_cuelga_de_la_de_arriba(session: Session, proyecto):
    padre = agregar(session, proyecto, "Padre", duracion=2)
    hija = agregar(session, proyecto, "Futura hija", duracion=3)
    arbol_service.indentar(session, hija.id)
    arbol = tasks_service.arbol(session, proyecto.id)
    assert [(t.titulo, n) for t, n in arbol] == [("Padre", 0), ("Futura hija", 1)]
    assert hija.codigo.startswith(padre.codigo + ".")


def test_indentar_la_primera_no_se_puede(session: Session, proyecto):
    primera = agregar(session, proyecto, "Primera")
    with pytest.raises(TareaInvalida):
        arbol_service.indentar(session, primera.id)


def test_desindentar_la_sube_de_nivel(session: Session, proyecto):
    padre = agregar(session, proyecto, "Padre")
    hija = agregar(session, proyecto, "Hija", parent=padre.id)
    arbol_service.desindentar(session, hija.id)
    arbol = tasks_service.arbol(session, proyecto.id)
    assert [(t.titulo, n) for t, n in arbol] == [("Padre", 0), ("Hija", 0)]


def test_desindentar_en_el_primer_nivel_no_se_puede(session: Session, proyecto):
    tarea = agregar(session, proyecto, "Sola")
    with pytest.raises(TareaInvalida):
        arbol_service.desindentar(session, tarea.id)


def test_renumerar_ordena_los_codigos(session: Session, proyecto):
    a = agregar(session, proyecto, "A")
    agregar(session, proyecto, "A1", parent=a.id)
    b = agregar(session, proyecto, "B")
    b.codigo = "99"
    session.add(b)
    session.commit()

    arbol_service.renumerar(session, proyecto.id)
    assert codigos(session, proyecto.id) == ["1", "1.1", "2"]


# --- predecesoras escritas a mano ---

def test_escribir_una_predecesora_por_codigo(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=3)
    b = agregar(session, proyecto, "B", duracion=2)
    avisos = predecesoras_service.guardar(session, proyecto.id, b.id, a.codigo)
    assert avisos == []
    plan = schedule_service.calcular(session, proyecto.id)
    assert plan.get(b.id).inicio == date(2026, 1, 8)


def test_el_lag_se_escribe_pegado_al_codigo(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=3)
    b = agregar(session, proyecto, "B", duracion=1)
    predecesoras_service.guardar(session, proyecto.id, b.id, f"{a.codigo}+2")
    plan = schedule_service.calcular(session, proyecto.id)
    assert plan.get(b.id).inicio == date(2026, 1, 12)


def test_lag_negativo_solapa(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=3)
    b = agregar(session, proyecto, "B", duracion=1)
    predecesoras_service.guardar(session, proyecto.id, b.id, f"{a.codigo}-1")
    plan = schedule_service.calcular(session, proyecto.id)
    assert plan.get(b.id).inicio == date(2026, 1, 7)


def test_varias_predecesoras_separadas_por_coma(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=2)
    b = agregar(session, proyecto, "B", duracion=5)
    c = agregar(session, proyecto, "C", duracion=1)
    predecesoras_service.guardar(session, proyecto.id, c.id, f"{a.codigo}, {b.codigo}")
    assert predecesoras_service.texto_de(session, proyecto.id, c.id) == "1, 2"


def test_borrar_el_texto_borra_las_dependencias(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=2)
    b = agregar(session, proyecto, "B", duracion=2)
    predecesoras_service.guardar(session, proyecto.id, b.id, a.codigo)
    predecesoras_service.guardar(session, proyecto.id, b.id, "")
    assert predecesoras_service.texto_de(session, proyecto.id, b.id) == ""


def test_un_codigo_que_no_existe_avisa(session: Session, proyecto):
    a = agregar(session, proyecto, "A")
    avisos = predecesoras_service.guardar(session, proyecto.id, a.id, "9.9")
    assert "9.9" in avisos[0]


def test_texto_sin_sentido_avisa(session: Session, proyecto):
    a = agregar(session, proyecto, "A")
    avisos = predecesoras_service.guardar(session, proyecto.id, a.id, "la anterior")
    assert "no se entiende" in avisos[0]


def test_un_ciclo_se_rechaza(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=2)
    b = agregar(session, proyecto, "B", duracion=2)
    predecesoras_service.guardar(session, proyecto.id, b.id, a.codigo)
    avisos = predecesoras_service.guardar(session, proyecto.id, a.id, b.codigo)
    assert "ciclo" in avisos[0].lower()
    assert predecesoras_service.texto_de(session, proyecto.id, a.id) == ""


def test_cambiar_el_lag_no_duplica_la_dependencia(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=2)
    b = agregar(session, proyecto, "B", duracion=2)
    predecesoras_service.guardar(session, proyecto.id, b.id, a.codigo)
    predecesoras_service.guardar(session, proyecto.id, b.id, f"{a.codigo}+4")
    assert predecesoras_service.texto_de(session, proyecto.id, b.id) == "1+4"


# --- notación de tipos de dependencia en la celda ---

def test_ss_se_escribe_pegado_al_codigo(session: Session, proyecto):
    a = agregar(session, proyecto, "Ejecución", duracion=30)
    b = agregar(session, proyecto, "Supervisión", duracion=30)
    avisos = predecesoras_service.guardar(session, proyecto.id, b.id, f"{a.codigo}SS")
    assert avisos == []
    plan = schedule_service.calcular(session, proyecto.id)
    assert plan.get(a.id).inicio == plan.get(b.id).inicio


def test_ff_se_escribe_pegado_al_codigo(session: Session, proyecto):
    a = agregar(session, proyecto, "Larga", duracion=10)
    b = agregar(session, proyecto, "Cierra con la larga", duracion=3)
    predecesoras_service.guardar(session, proyecto.id, b.id, f"{a.codigo}FF")
    plan = schedule_service.calcular(session, proyecto.id)
    assert plan.get(a.id).fin == plan.get(b.id).fin


def test_el_tipo_y_el_lag_conviven(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=10)
    b = agregar(session, proyecto, "B", duracion=3)
    predecesoras_service.guardar(session, proyecto.id, b.id, f"{a.codigo}SS+2")
    assert predecesoras_service.texto_de(session, proyecto.id, b.id) == "1SS+2"


def test_la_celda_muestra_el_tipo_que_guardaste(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=5)
    b = agregar(session, proyecto, "B", duracion=5)
    for escrito, esperado in [("1SS", "1SS"), ("1FF-1", "1FF-1"), ("1", "1"), ("1+3", "1+3")]:
        predecesoras_service.guardar(session, proyecto.id, b.id, escrito)
        assert predecesoras_service.texto_de(session, proyecto.id, b.id) == esperado


def test_cambiar_de_tipo_no_duplica_la_dependencia(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=5)
    b = agregar(session, proyecto, "B", duracion=5)
    predecesoras_service.guardar(session, proyecto.id, b.id, a.codigo)
    predecesoras_service.guardar(session, proyecto.id, b.id, f"{a.codigo}SS")
    assert len(dependencies_service.listar(session, proyecto.id)) == 1


def test_un_tipo_inventado_avisa(session: Session, proyecto):
    a = agregar(session, proyecto, "A")
    avisos = predecesoras_service.guardar(session, proyecto.id, a.id, "1XY")
    assert "no se entiende" in avisos[0]
