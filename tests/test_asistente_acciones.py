"""El contrato de acciones (Fase 29b): nada sin OK, y lo inválido rebota con aviso."""

import pytest
from sqlmodel import Session

from app.schemas import TareaIn
from app.services import arbol as arbol_service
from app.services import asistente
from app.services import asistente_acciones as acciones_service
from app.services import tasks as tasks_service
from app.services import vista as vista_service

from .test_app import cliente_fixture  # noqa: F401 — fixture `cliente`


def poblar(session, proyecto):
    etapa = arbol_service.agregar_al_final(session, proyecto.id, TareaIn(titulo="Etapa 1"))
    hija = arbol_service.agregar_al_final(
        session, proyecto.id, TareaIn(titulo="Relevamiento", duracion=5, parent_id=etapa.id)
    )
    suelta = arbol_service.agregar_al_final(
        session, proyecto.id, TareaIn(titulo="Cierre", duracion=2)
    )
    return etapa, hija, suelta


# --- parseo: input externo, cero confianza ---

def test_desde_json_corrupto_avisa_sin_reventar():
    acciones, avisos = acciones_service.desde_json("{esto no es json")
    assert acciones == [] and avisos


def test_el_exceso_de_acciones_se_recorta_con_aviso():
    crudas = [{"tipo": "crear_tarea", "titulo": f"T{i}"} for i in range(25)]
    acciones, avisos = acciones_service.parsear(crudas)
    assert len(acciones) == acciones_service.MAX_ACCIONES
    assert any("las primeras" in a for a in avisos)


def test_las_acciones_viajan_y_vuelven_iguales():
    acciones, _ = acciones_service.parsear(
        [{"tipo": "cambiar_predecesoras", "wbs": "2", "predecesoras": "1.1+2"}]
    )
    de_vuelta, avisos = acciones_service.desde_json(acciones_service.a_json(acciones))
    assert avisos == [] and de_vuelta == acciones


# --- aplicar: siempre vía services, lo inválido rebota ---

def test_crear_bajo_un_padre_por_wbs(session: Session, proyecto):
    etapa, _, _ = poblar(session, proyecto)
    acciones, _ = acciones_service.parsear([{
        "tipo": "crear_tarea", "titulo": "Pruebas integrales",
        "padre_wbs": etapa.codigo, "duracion": 4,
    }])
    avisos = acciones_service.aplicar(session, proyecto.id, acciones)

    assert avisos == []
    nueva = next(
        t for t in tasks_service.listar(session, proyecto.id) if t.titulo == "Pruebas integrales"
    )
    assert nueva.parent_id == etapa.id and nueva.duracion == 4


def test_crear_con_padre_inexistente_va_al_primer_nivel_con_aviso(session: Session, proyecto):
    poblar(session, proyecto)
    acciones, _ = acciones_service.parsear([
        {"tipo": "crear_tarea", "titulo": "Huérfana", "padre_wbs": "9.9"}
    ])
    avisos = acciones_service.aplicar(session, proyecto.id, acciones)

    assert any("9.9" in a for a in avisos)
    nueva = next(t for t in tasks_service.listar(session, proyecto.id) if t.titulo == "Huérfana")
    assert nueva.parent_id is None


def test_modificar_duracion_por_wbs(session: Session, proyecto):
    _, hija, _ = poblar(session, proyecto)
    acciones, _ = acciones_service.parsear([
        {"tipo": "modificar_tarea", "wbs": hija.codigo, "duracion": 9, "critica": True}
    ])
    assert acciones_service.aplicar(session, proyecto.id, acciones) == []

    actual = tasks_service.obtener(session, hija.id)
    assert actual.duracion == 9 and actual.critica is True
    assert actual.titulo == "Relevamiento"  # lo no pedido no se toca


def test_modificar_un_wbs_inexistente_avisa(session: Session, proyecto):
    poblar(session, proyecto)
    acciones, _ = acciones_service.parsear([
        {"tipo": "modificar_tarea", "wbs": "9.9", "duracion": 3}
    ])
    avisos = acciones_service.aplicar(session, proyecto.id, acciones)
    assert any("9.9" in a for a in avisos)


def test_cambiar_predecesoras_crea_la_dependencia(session: Session, proyecto):
    _, hija, suelta = poblar(session, proyecto)
    acciones, _ = acciones_service.parsear([
        {"tipo": "cambiar_predecesoras", "wbs": suelta.codigo, "predecesoras": hija.codigo}
    ])
    assert acciones_service.aplicar(session, proyecto.id, acciones) == []

    datos = vista_service.armar(session, proyecto.id)
    fila = next(f for f in datos.todas_las_filas if f.tarea.id == suelta.id)
    assert fila.predecesoras_texto == hija.codigo


def test_un_ciclo_propuesto_rebota_con_el_aviso_del_motor(session: Session, proyecto):
    _, hija, suelta = poblar(session, proyecto)
    bien, _ = acciones_service.parsear([
        {"tipo": "cambiar_predecesoras", "wbs": suelta.codigo, "predecesoras": hija.codigo}
    ])
    acciones_service.aplicar(session, proyecto.id, bien)

    ciclo, _ = acciones_service.parsear([
        {"tipo": "cambiar_predecesoras", "wbs": hija.codigo, "predecesoras": suelta.codigo}
    ])
    avisos = acciones_service.aplicar(session, proyecto.id, ciclo)
    assert any("ciclo" in a.lower() for a in avisos)


def test_las_dependencias_no_van_en_resumenes(session: Session, proyecto):
    etapa, _, suelta = poblar(session, proyecto)
    acciones, _ = acciones_service.parsear([
        {"tipo": "cambiar_predecesoras", "wbs": etapa.codigo, "predecesoras": suelta.codigo}
    ])
    avisos = acciones_service.aplicar(session, proyecto.id, acciones)
    assert any("subtareas" in a for a in avisos)


# --- el criterio de la fase: NADA se aplica sin confirmación ---

def test_preguntar_jamas_escribe_aunque_el_modelo_proponga(cliente, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_de_prueba")
    crudo = (
        '{"analisis": "Sumo una tarea.", "acciones": ['
        '{"tipo": "crear_tarea", "titulo": "Colada del asistente", "duracion": 3}]}'
    )
    monkeypatch.setattr(asistente, "_completar", lambda k, m: crudo)
    cliente.post(
        "/proyectos",
        data={"nombre": "Con OK", "descripcion": "", "fecha_inicio": "2026-01-05"},
        follow_redirects=True,
    )
    cliente.post("/proyectos/1/tareas/agregar")

    respuesta = cliente.post("/proyectos/1/asistente", data={"pregunta": "sumá pruebas"})
    assert "Colada del asistente" in respuesta.text  # se propone…
    tablero = cliente.get("/proyectos/1")
    assert "Colada del asistente" not in tablero.text  # …pero NO se aplicó

    # Recién la confirmación explícita escribe.
    import json
    carga = json.dumps([
        {"tipo": "crear_tarea", "titulo": "Colada del asistente",
         "padre_wbs": "", "duracion": 3, "predecesoras": "", "critica": False}
    ])
    aplicado = cliente.post("/proyectos/1/asistente/aplicar", data={"carga": carga})
    assert "1 cambios del asistente aplicados" in aplicado.text
    assert "Colada del asistente" in cliente.get("/proyectos/1").text


def test_aplicar_con_carga_corrupta_avisa_sin_500(cliente):
    cliente.post(
        "/proyectos",
        data={"nombre": "Carga rota", "descripcion": "", "fecha_inicio": "2026-01-05"},
        follow_redirects=True,
    )
    respuesta = cliente.post("/proyectos/1/asistente/aplicar", data={"carga": "{roto"})
    assert respuesta.status_code == 200
    assert "Volvé a preguntar" in respuesta.text
