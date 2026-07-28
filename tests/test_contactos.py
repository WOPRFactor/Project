"""Responsables como personas del proyecto, no como texto suelto por tarea.

Lo que se cuida acá: escribir el mismo nombre de dos formas no crea dos personas, y
nada de lo que la app decide sola se lleva puesto trabajo del usuario.
"""

import pytest
from sqlalchemy import inspect, text
from sqlmodel import Session

from app.schemas import TareaIn
from app.services import arbol as arbol_service
from app.services import contactos as contactos_service
from app.services import projects as projects_service
from app.services import tasks as tasks_service
from app.services import vista as vista_service
from app.services.contactos import ContactoInvalido, normalizar

from .test_migraciones import base_vieja, migrar_todo


def agregar(session, proyecto, titulo, responsable=""):
    return arbol_service.agregar_al_final(
        session, proyecto.id, TareaIn(titulo=titulo, responsable=responsable)
    )


# --- normalización: qué cuenta como la misma persona ---

def test_las_mayusculas_no_hacen_una_persona_nueva():
    assert normalizar("Ariel") == normalizar("ariel") == normalizar("  ARIEL  ")


def test_los_acentos_tampoco():
    assert normalizar("Martín") == normalizar("Martin")


def test_los_espacios_de_mas_se_colapsan():
    assert normalizar("Ariel   Clerici") == normalizar("Ariel Clerici")


def test_nombres_distintos_siguen_siendo_distintos():
    """La normalización no adivina: «A. Clerici» y «Ariel Clerici» los une una persona."""
    assert normalizar("A. Clerici") != normalizar("Ariel Clerici")


# --- resolver: la celda de la grilla sigue siendo texto libre ---

def test_escribir_un_nombre_nuevo_crea_la_persona(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A", responsable="Ariel")

    personas = contactos_service.listar(session, proyecto.id)
    assert [p.nombre for p in personas] == ["Ariel"]
    assert tarea.responsable_id == personas[0].id


def test_escribirlo_distinto_no_duplica(session: Session, proyecto):
    a = agregar(session, proyecto, "A", responsable="Ariel")
    b = agregar(session, proyecto, "B", responsable="  ariel ")

    assert len(contactos_service.listar(session, proyecto.id)) == 1
    assert a.responsable_id == b.responsable_id


def test_se_guarda_la_primera_forma_escrita(session: Session, proyecto):
    agregar(session, proyecto, "A", responsable="Ariel Clerici")
    agregar(session, proyecto, "B", responsable="ariel clerici")
    assert contactos_service.listar(session, proyecto.id)[0].nombre == "Ariel Clerici"


def test_vacio_es_sin_asignar_y_no_crea_nada(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A", responsable="   ")

    assert tarea.responsable_id is None
    assert contactos_service.listar(session, proyecto.id) == []


def test_borrar_el_nombre_deja_la_tarea_sin_asignar(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A", responsable="Ariel")
    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", responsable=""))

    assert tasks_service.obtener(session, tarea.id).responsable_id is None
    # la persona sigue existiendo: se sacó de una tarea, no del proyecto
    assert len(contactos_service.listar(session, proyecto.id)) == 1


def test_cada_proyecto_tiene_su_gente(session: Session, proyecto):
    from datetime import date

    from app.schemas import ProyectoIn

    otro = projects_service.crear(
        session, ProyectoIn(nombre="Otro", fecha_inicio=date(2026, 1, 5))
    )
    agregar(session, proyecto, "A", responsable="Ariel")
    arbol_service.agregar_al_final(
        session, otro.id, TareaIn(titulo="B", responsable="Ariel")
    )

    assert len(contactos_service.listar(session, proyecto.id)) == 1
    assert len(contactos_service.listar(session, otro.id)) == 1
    # son dos filas distintas: un proyecto no puede ver la gente de otro
    assert contactos_service.listar(session, proyecto.id)[0].id != \
        contactos_service.listar(session, otro.id)[0].id


def test_la_vista_trae_la_persona_resuelta(session: Session, proyecto):
    agregar(session, proyecto, "A", responsable="Ariel")
    fila = vista_service.armar(session, proyecto.id).filas[0]
    assert fila.responsable.nombre == "Ariel"


# --- unir lo que la app no puede adivinar ---

def test_unir_reasigna_las_tareas_y_borra_el_duplicado(session: Session, proyecto):
    agregar(session, proyecto, "A", responsable="A. Clerici")
    agregar(session, proyecto, "B", responsable="Ariel Clerici")
    personas = {p.nombre: p for p in contactos_service.listar(session, proyecto.id)}

    movidas = contactos_service.unir(
        session, personas["A. Clerici"].id, personas["Ariel Clerici"].id
    )

    assert movidas == 1
    quedan = contactos_service.listar(session, proyecto.id)
    assert [p.nombre for p in quedan] == ["Ariel Clerici"]
    assert all(t.responsable_id == quedan[0].id for t in tasks_service.listar(session, proyecto.id))


def test_no_se_une_con_alguien_de_otro_proyecto(session: Session, proyecto):
    from datetime import date

    from app.schemas import ProyectoIn

    otro = projects_service.crear(
        session, ProyectoIn(nombre="Otro", fecha_inicio=date(2026, 1, 5))
    )
    mio = contactos_service.resolver(session, proyecto.id, "Ariel")
    ajeno = contactos_service.resolver(session, otro.id, "Alguien")

    with pytest.raises(ContactoInvalido):
        contactos_service.unir(session, mio, ajeno)


def test_renombrar_a_un_nombre_ya_usado_se_rechaza(session: Session, proyecto):
    uno = contactos_service.resolver(session, proyecto.id, "Ariel")
    contactos_service.resolver(session, proyecto.id, "Martín")

    with pytest.raises(ContactoInvalido, match="Unir"):
        contactos_service.renombrar(session, uno, "martin")


def test_renombrar_sin_choque_funciona(session: Session, proyecto):
    uno = contactos_service.resolver(session, proyecto.id, "Ariel")
    actualizado = contactos_service.renombrar(session, uno, "Ariel Clerici", "a@c.com")

    assert actualizado.nombre == "Ariel Clerici"
    assert actualizado.mail == "a@c.com"
    # y la clave se recalcula, si no el próximo "ariel clerici" duplicaría
    assert contactos_service.buscar(session, proyecto.id, "ARIEL CLERICI").id == uno


def test_borrar_una_persona_no_borra_sus_tareas(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A", responsable="Ariel")
    persona = contactos_service.listar(session, proyecto.id)[0]

    contactos_service.eliminar(session, persona.id)

    assert tasks_service.obtener(session, tarea.id) is not None
    assert tasks_service.obtener(session, tarea.id).responsable_id is None


def test_borrar_el_proyecto_se_lleva_su_gente(session: Session, proyecto):
    agregar(session, proyecto, "A", responsable="Ariel")
    projects_service.eliminar(session, proyecto.id)
    assert contactos_service.listar(session, proyecto.id) == []


# --- migración desde la versión anterior ---

def _base_con_responsables(tmp_path):
    engine = base_vieja(tmp_path)
    with engine.begin() as conexion:
        conexion.execute(text(
            "ALTER TABLE task ADD COLUMN responsable VARCHAR NOT NULL DEFAULT ''"
        ))
        conexion.execute(text(
            "INSERT INTO project (nombre, descripcion, fecha_inicio, estado) "
            "VALUES ('Viejo', '', '2026-01-05', 'activo')"
        ))
        for titulo, quien in [("A", "Ariel"), ("B", "ariel"), ("C", "Martín"), ("D", "")]:
            conexion.execute(text(
                "INSERT INTO task (project_id, titulo, notas, duracion, estado, orden, responsable) "
                f"VALUES (1, '{titulo}', '', 3, 'pendiente', 0, '{quien}')"
            ))
    return engine


def test_los_responsables_viejos_se_convierten_en_personas(tmp_path):
    engine = _base_con_responsables(tmp_path)

    migrar_todo(engine)

    with Session(engine) as session:
        personas = contactos_service.listar(session, 1)
        # «Ariel» y «ariel» entran como una sola
        assert sorted(p.nombre for p in personas) == ["Ariel", "Martín"]
        por_titulo = {t.titulo: t for t in tasks_service.listar(session, 1)}
        assert por_titulo["A"].responsable_id == por_titulo["B"].responsable_id
        assert por_titulo["D"].responsable_id is None


def test_la_columna_vieja_desaparece(tmp_path):
    engine = _base_con_responsables(tmp_path)
    migrar_todo(engine)
    assert "responsable" not in {c["name"] for c in inspect(engine).get_columns("task")}


def test_migrar_dos_veces_no_duplica_personas(tmp_path):
    engine = _base_con_responsables(tmp_path)
    migrar_todo(engine)
    migrar_todo(engine)
    with Session(engine) as session:
        assert len(contactos_service.listar(session, 1)) == 2
