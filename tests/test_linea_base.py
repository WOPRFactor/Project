"""Línea base sobre un proyecto: congelar, medir el desvío y no romper nada sin base."""

from datetime import date

import pytest
from sqlmodel import Session

from app.schemas import ProyectoIn, TareaIn
from app.services import arbol as arbol_service
from app.services import linea_base as linea_base_service
from app.services import predecesoras as predecesoras_service
from app.services import projects as projects_service
from app.services import tasks as tasks_service
from app.services import vista as vista_service
from app.services.linea_base import LineaBaseInvalida


def agregar(session, proyecto, titulo, duracion=1, peso=None):
    return arbol_service.agregar_al_final(
        session, proyecto.id, TareaIn(titulo=titulo, duracion=duracion, peso=peso)
    )


def congelar(session, proyecto, nombre="Aprobada"):
    datos = vista_service.armar(session, proyecto.id)
    return linea_base_service.congelar(session, proyecto.id, datos, nombre)


def vista_con_base(session, proyecto):
    base = linea_base_service.fechas_base(session, proyecto.id)
    return vista_service.armar(session, proyecto.id, base=base)


def filas(session, proyecto):
    return {f.tarea.titulo: f for f in vista_con_base(session, proyecto).todas_las_filas}


# --- congelar ---

def test_congelar_guarda_una_foto_de_cada_tarea(session: Session, proyecto):
    agregar(session, proyecto, "A", duracion=5, peso=50)
    agregar(session, proyecto, "B", duracion=3, peso=50)

    linea = congelar(session, proyecto)

    assert linea.vigente
    assert len(linea_base_service.tareas_de(session, linea.id)) == 2


def test_congelar_no_toca_ninguna_fecha_del_cronograma_vivo(session: Session, proyecto):
    agregar(session, proyecto, "A", duracion=5)
    antes = vista_service.armar(session, proyecto.id).resumen

    congelar(session, proyecto)

    despues = vista_service.armar(session, proyecto.id).resumen
    assert (despues.inicio, despues.fin) == (antes.inicio, antes.fin)


def test_no_se_congela_con_los_pesos_abiertos(session: Session, proyecto):
    """Prometer con una cuenta que no cierra hace que todo avance posterior sea inventado."""
    agregar(session, proyecto, "A", peso=40)
    agregar(session, proyecto, "B", peso=30)

    with pytest.raises(LineaBaseInvalida, match="pesos no cierran"):
        congelar(session, proyecto)


def test_no_se_congela_un_proyecto_vacio(session: Session, proyecto):
    with pytest.raises(LineaBaseInvalida):
        congelar(session, proyecto)


def test_congelar_de_nuevo_desplaza_a_la_anterior(session: Session, proyecto):
    agregar(session, proyecto, "A")
    primera = congelar(session, proyecto, "Primera")
    segunda = congelar(session, proyecto, "Replanificada")

    vigentes = [l for l in linea_base_service.listar(session, proyecto.id) if l.vigente]
    assert [l.id for l in vigentes] == [segunda.id]
    assert linea_base_service.vigente(session, proyecto.id).nombre == "Replanificada"
    assert primera.id != segunda.id


def test_se_puede_volver_a_una_base_anterior(session: Session, proyecto):
    agregar(session, proyecto, "A")
    primera = congelar(session, proyecto, "Primera")
    congelar(session, proyecto, "Segunda")

    linea_base_service.marcar_vigente(session, proyecto.id, primera.id)

    assert linea_base_service.vigente(session, proyecto.id).id == primera.id


# --- desvío ---

def test_sin_base_no_hay_desvio_y_nada_se_rompe(session: Session, proyecto):
    agregar(session, proyecto, "A", duracion=5)
    fila = filas(session, proyecto)["A"]
    assert fila.desvio is None and not fila.es_nueva
    assert linea_base_service.fechas_base(session, proyecto.id) == {}


def test_alargar_una_tarea_la_muestra_atrasada(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A", duracion=5)
    congelar(session, proyecto)

    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", duracion=8))

    assert filas(session, proyecto)["A"].desvio == 3


def test_acortarla_la_muestra_adelantada(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A", duracion=8)
    congelar(session, proyecto)

    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", duracion=5))

    assert filas(session, proyecto)["A"].desvio == -3


def test_sin_cambios_el_desvio_es_cero(session: Session, proyecto):
    agregar(session, proyecto, "A", duracion=5)
    congelar(session, proyecto)
    assert filas(session, proyecto)["A"].desvio == 0


def test_una_tarea_agregada_despues_es_nueva_no_atrasada(session: Session, proyecto):
    agregar(session, proyecto, "A", duracion=5)
    congelar(session, proyecto)

    agregar(session, proyecto, "Alcance extra", duracion=10)

    extra = filas(session, proyecto)["Alcance extra"]
    assert extra.es_nueva and extra.desvio is None


def test_el_atraso_se_propaga_por_las_dependencias(session: Session, proyecto):
    """Es el caso que importa: mover una tarea corre todo lo que venía atrás."""
    a = agregar(session, proyecto, "A", duracion=5)
    b = agregar(session, proyecto, "B", duracion=5)
    predecesoras_service.guardar(session, proyecto.id, b.id, a.codigo)
    congelar(session, proyecto)

    tasks_service.actualizar(session, a.id, TareaIn(titulo="A", duracion=15))

    resultado = filas(session, proyecto)
    assert resultado["A"].desvio == 10
    assert resultado["B"].desvio == 10


def test_mover_el_arranque_del_proyecto_corre_todo(session: Session, proyecto):
    agregar(session, proyecto, "A", duracion=5)
    congelar(session, proyecto)

    projects_service.actualizar(
        session, proyecto.id,
        ProyectoIn(nombre=proyecto.nombre, fecha_inicio=date(2026, 1, 12)),
    )

    assert filas(session, proyecto)["A"].desvio == 5


def test_la_barra_de_la_base_se_puede_dibujar(session: Session, proyecto):
    agregar(session, proyecto, "A", duracion=5)
    congelar(session, proyecto)
    assert filas(session, proyecto)["A"].columnas_base is not None


# --- desvío por ámbito ---

def test_el_desvio_del_bloque_no_suma_tareas_en_paralelo(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=5)
    b = agregar(session, proyecto, "B", duracion=5)
    congelar(session, proyecto)

    for tarea in (a, b):
        tasks_service.actualizar(session, tarea.id, TareaIn(titulo=tarea.titulo, duracion=10))

    datos = vista_con_base(session, proyecto)
    assert linea_base_service.desvio_por_ambito(session, proyecto.id, datos)["proyecto"] == 5


def test_sin_base_el_desvio_por_ambito_es_vacio(session: Session, proyecto):
    agregar(session, proyecto, "A")
    datos = vista_service.armar(session, proyecto.id)
    assert linea_base_service.desvio_por_ambito(session, proyecto.id, datos) == {}


# --- borrado ---

def test_borrar_una_base_no_toca_las_tareas(session: Session, proyecto):
    agregar(session, proyecto, "A")
    linea = congelar(session, proyecto)

    linea_base_service.eliminar(session, linea.id)

    assert linea_base_service.listar(session, proyecto.id) == []
    assert len(tasks_service.listar(session, proyecto.id)) == 1


def test_borrar_el_proyecto_se_lleva_sus_bases(session: Session, proyecto):
    agregar(session, proyecto, "A")
    congelar(session, proyecto)

    projects_service.eliminar(session, proyecto.id)

    assert linea_base_service.listar(session, proyecto.id) == []
