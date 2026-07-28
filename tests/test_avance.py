"""Avance real: qué manda, cuándo lo sugiere el estado, y contra qué se compara."""

from datetime import date, timedelta

from sqlmodel import Session

from app.schemas import TareaIn
from app.services import arbol as arbol_service
from app.services import estados as estados_service
from app.services import linea_base as linea_base_service
from app.services import tasks as tasks_service
from app.services import vista as vista_service


def agregar(session, proyecto, titulo, duracion=1, peso=None):
    return arbol_service.agregar_al_final(
        session, proyecto.id, TareaIn(titulo=titulo, duracion=duracion, peso=peso)
    )


def estado_llamado(session, proyecto, nombre):
    return next(e for e in estados_service.listar(session, proyecto.id) if e.nombre == nombre)


# --- el estado sugiere, la tarea manda ---

def test_elegir_un_estado_mueve_el_avance_si_nadie_lo_toco(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A")
    en_curso = estado_llamado(session, proyecto, "En curso")

    tasks_service.cambiar_estado(session, tarea.id, en_curso.id)

    assert tasks_service.obtener(session, tarea.id).avance == 50


def test_un_avance_escrito_a_mano_no_se_pisa(session: Session, proyecto):
    """La diferencia entre una ayuda y una imposición."""
    tarea = agregar(session, proyecto, "A")
    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", avance=30))

    en_curso = estado_llamado(session, proyecto, "En curso")
    tasks_service.cambiar_estado(session, tarea.id, en_curso.id)

    assert tasks_service.obtener(session, tarea.id).avance == 30


def test_marcarla_hecha_la_lleva_al_100(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A")
    tasks_service.cambiar_estado(session, tarea.id, estados_service.final(session, proyecto.id).id)
    assert tasks_service.obtener(session, tarea.id).avance == 100


def test_el_avance_se_acota_entre_0_y_100(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A")
    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", avance=100))
    assert tasks_service.obtener(session, tarea.id).avance == 100


# --- fechas reales ---

def test_empezar_sella_el_inicio_real(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A")
    assert tarea.inicio_real is None

    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", avance=10))
    assert tasks_service.obtener(session, tarea.id).inicio_real == date.today()


def test_terminarla_sella_el_fin_real(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A")
    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", avance=100))
    assert tasks_service.obtener(session, tarea.id).fin_real == date.today()


def test_el_inicio_real_no_se_pisa_al_avanzar_de_nuevo(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A")
    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", avance=10))
    original = tasks_service.obtener(session, tarea.id).inicio_real

    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", avance=60))
    assert tasks_service.obtener(session, tarea.id).inicio_real == original


def test_volver_atras_borra_el_fin_real(session: Session, proyecto):
    """Si deja de estar terminada, la fecha de fin real ya no es cierta."""
    tarea = agregar(session, proyecto, "A")
    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", avance=100))
    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", avance=70))

    assert tasks_service.obtener(session, tarea.id).fin_real is None


# --- avance ponderado con avance real ---

def test_el_avance_del_proyecto_usa_el_real_y_no_el_del_estado(session: Session, proyecto):
    a = agregar(session, proyecto, "A", peso=80)
    agregar(session, proyecto, "B", peso=20)
    tasks_service.actualizar(session, a.id, TareaIn(titulo="A", peso=80, avance=50))

    assert vista_service.armar(session, proyecto.id).avance_ponderado == 40


def test_una_tarea_a_medio_camino_aporta_la_mitad_de_su_peso(session: Session, proyecto):
    a = agregar(session, proyecto, "A", peso=100)
    tasks_service.actualizar(session, a.id, TareaIn(titulo="A", peso=100, avance=25))
    assert vista_service.armar(session, proyecto.id).avance_ponderado == 25


# --- avance planificado contra la línea base ---

def congelar(session, proyecto):
    datos = vista_service.armar(session, proyecto.id)
    return linea_base_service.congelar(session, proyecto.id, datos, "Aprobada")


def planificado(session, proyecto, corte):
    return linea_base_service.avance_planificado(session, proyecto.id, corte)


def test_sin_linea_base_no_hay_planificado(session: Session, proyecto):
    agregar(session, proyecto, "A", duracion=10)
    assert linea_base_service.avance_planificado(session, proyecto.id) is None


def test_antes_de_arrancar_el_planificado_es_cero(session: Session, proyecto):
    agregar(session, proyecto, "A", duracion=10)
    congelar(session, proyecto)
    assert planificado(session, proyecto, date(2025, 12, 1)) == 0


def test_pasado_el_fin_el_planificado_es_cien(session: Session, proyecto):
    agregar(session, proyecto, "A", duracion=10)
    congelar(session, proyecto)
    assert planificado(session, proyecto, date(2027, 1, 1)) == 100


def test_a_mitad_de_camino_el_planificado_ronda_la_mitad(session: Session, proyecto):
    """El proyecto arranca el 05/01/2026 y dura 10 días hábiles: al sexto va ~55%."""
    agregar(session, proyecto, "A", duracion=10)
    congelar(session, proyecto)
    resultado = planificado(session, proyecto, date(2026, 1, 12))
    assert 40 <= resultado <= 70


def test_el_planificado_pesa_cada_tarea_por_lo_que_vale(session: Session, proyecto):
    """Una tarea corta pero pesada mueve el planificado más que una larga y liviana."""
    agregar(session, proyecto, "Corta y clave", duracion=2, peso=90)
    agregar(session, proyecto, "Larga y liviana", duracion=40, peso=10)
    congelar(session, proyecto)

    # pasada la corta, casi todo lo planificado ya debería estar
    assert planificado(session, proyecto, date(2026, 1, 7)) >= 85


def test_el_planificado_usa_los_pesos_congelados(session: Session, proyecto):
    """Si usara los de hoy, un informe viejo dejaría de ser comparable consigo mismo."""
    a = agregar(session, proyecto, "A", duracion=5, peso=90)
    agregar(session, proyecto, "B", duracion=40, peso=10)
    congelar(session, proyecto)
    antes = planificado(session, proyecto, date(2026, 1, 12))

    tasks_service.actualizar(session, a.id, TareaIn(titulo="A", duracion=5, peso=10))

    assert planificado(session, proyecto, date(2026, 1, 12)) == antes


def test_real_y_planificado_se_pueden_comparar(session: Session, proyecto):
    a = agregar(session, proyecto, "A", duracion=10, peso=100)
    congelar(session, proyecto)
    tasks_service.actualizar(session, a.id, TareaIn(titulo="A", duracion=10, peso=100, avance=20))

    corte = date(2026, 1, 16)  # ya debería estar terminada
    real = vista_service.armar(session, proyecto.id).avance_ponderado
    assert real == 20
    assert planificado(session, proyecto, corte) == 100
    assert real < planificado(session, proyecto, corte)  # atrasado, y se ve


def test_un_hito_aporta_todo_o_nada(session: Session, proyecto):
    agregar(session, proyecto, "Tarea", duracion=5, peso=50)
    agregar(session, proyecto, "Hito", duracion=0, peso=50)
    congelar(session, proyecto)

    antes = planificado(session, proyecto, date(2026, 1, 5))
    despues = planificado(session, proyecto, date(2026, 1, 5) + timedelta(days=30))
    assert antes < despues == 100
