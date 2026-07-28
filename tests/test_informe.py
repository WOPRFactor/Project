"""El informe de estado.

El criterio de esta fase es uno solo y es duro: **los números del informe tienen que
coincidir con los del tablero**. Un informe que no coincide con la pantalla hace más
daño que no tener informe, porque se manda a un cliente.
"""

from datetime import date

import pytest
from sqlmodel import Session

from app.schemas import RiesgoIn, TareaIn
from app.services import arbol as arbol_service
from app.services import estados as estados_service
from app.services import informe as informe_service
from app.services import linea_base as linea_base_service
from app.services import pesos_aplicar
from app.services import predecesoras as predecesoras_service
from app.services import riesgos as riesgos_service
from app.services import tasks as tasks_service
from app.services import vista as vista_service
from app.services.informe import InformeInvalido


def agregar(session, proyecto, titulo, duracion=1, peso=None):
    return arbol_service.agregar_al_final(
        session, proyecto.id, TareaIn(titulo=titulo, duracion=duracion, peso=peso)
    )


def poblar(session, proyecto):
    etapa = agregar(session, proyecto, "Etapa 1", peso=60)
    a = agregar(session, proyecto, "Relevamiento", duracion=10, peso=50)
    b = agregar(session, proyecto, "Análisis", duracion=10, peso=50)
    for hija in (a, b):
        arbol_service.indentar(session, hija.id)
        tasks_service.mover(session, hija.id, etapa.id)
    predecesoras_service.guardar(session, proyecto.id, b.id, a.codigo)
    hito = agregar(session, proyecto, "Hito: etapa cerrada", duracion=0, peso=40)
    predecesoras_service.guardar(session, proyecto.id, hito.id, b.codigo)
    return {"etapa": etapa, "a": a, "b": b, "hito": hito}


def congelar(session, proyecto):
    datos = vista_service.armar(session, proyecto.id)
    return linea_base_service.congelar(session, proyecto.id, datos, "Aprobada")


# --- el criterio de la fase ---

def test_los_numeros_coinciden_con_los_del_tablero(session: Session, proyecto):
    creadas = poblar(session, proyecto)
    congelar(session, proyecto)
    tasks_service.actualizar(
        session, creadas["a"].id, TareaIn(titulo="Relevamiento", duracion=10, peso=50, avance=60)
    )

    tablero = vista_service.armar(session, proyecto.id)
    doc = informe_service.armar(session, proyecto.id)

    assert doc.avance_real == tablero.avance_ponderado
    assert doc.resumen.fin == tablero.resumen.fin
    assert doc.resumen.inicio == tablero.resumen.inicio
    assert doc.resumen.dias_habiles == tablero.resumen.dias_habiles
    assert doc.resumen.tareas == tablero.resumen.tareas
    assert doc.resumen.hitos == tablero.resumen.hitos


def test_el_desvio_del_informe_coincide_con_el_del_tablero(session: Session, proyecto):
    creadas = poblar(session, proyecto)
    congelar(session, proyecto)
    tasks_service.actualizar(
        session, creadas["a"].id, TareaIn(titulo="Relevamiento", duracion=20, peso=50)
    )

    base = linea_base_service.fechas_base(session, proyecto.id)
    tablero = vista_service.armar(session, proyecto.id, base=base)
    doc = informe_service.armar(session, proyecto.id)

    assert doc.desvio_ambito == linea_base_service.desvio_por_ambito(
        session, proyecto.id, tablero
    )


# --- no se emite cualquier cosa ---

def test_no_se_emite_con_los_pesos_abiertos(session: Session, proyecto):
    agregar(session, proyecto, "A", peso=40)
    agregar(session, proyecto, "B", peso=30)

    with pytest.raises(InformeInvalido, match="pesos no cierran"):
        informe_service.armar(session, proyecto.id)


def test_no_se_emite_un_proyecto_vacio(session: Session, proyecto):
    with pytest.raises(InformeInvalido):
        informe_service.armar(session, proyecto.id)


def test_un_proyecto_inexistente_da_error_claro(session: Session):
    with pytest.raises(InformeInvalido, match="no existe"):
        informe_service.armar(session, 9999)


# --- sin línea base sigue siendo útil ---

def test_sin_base_se_emite_pero_sin_desvio(session: Session, proyecto):
    poblar(session, proyecto)
    doc = informe_service.armar(session, proyecto.id)

    assert not doc.hay_base
    assert doc.avance_planificado is None and doc.brecha is None
    assert doc.desvio_ambito == {}
    assert doc.resumen.fin is not None  # el estado sí se puede leer


# --- contenido ---

def test_las_atrasadas_salen_con_la_peor_primero(session: Session, proyecto):
    creadas = poblar(session, proyecto)
    congelar(session, proyecto)
    tasks_service.actualizar(
        session, creadas["a"].id, TareaIn(titulo="Relevamiento", duracion=30, peso=50)
    )

    doc = informe_service.armar(session, proyecto.id)
    assert doc.atrasadas
    assert doc.atrasadas[0].desvio >= doc.atrasadas[-1].desvio
    assert all(f.desvio > 0 for f in doc.atrasadas)


def test_sin_movimientos_no_hay_atrasadas(session: Session, proyecto):
    poblar(session, proyecto)
    congelar(session, proyecto)
    assert informe_service.armar(session, proyecto.id).atrasadas == []


def test_en_riesgo_son_las_sin_holgura_todavia_sin_terminar(session: Session, proyecto):
    """Distinto de atrasada: todavía no pasó nada, pero no hay colchón."""
    poblar(session, proyecto)
    doc = informe_service.armar(session, proyecto.id)

    assert doc.en_riesgo
    assert all(f.sin_holgura for f in doc.en_riesgo)


def test_una_tarea_terminada_sale_de_en_riesgo(session: Session, proyecto):
    creadas = poblar(session, proyecto)
    hecha = estados_service.final(session, proyecto.id)
    tasks_service.cambiar_estado(session, creadas["a"].id, hecha.id)

    doc = informe_service.armar(session, proyecto.id)
    assert creadas["a"].id not in {f.tarea.id for f in doc.en_riesgo}


def test_los_hitos_van_con_su_fecha_comprometida(session: Session, proyecto):
    creadas = poblar(session, proyecto)
    congelar(session, proyecto)
    tasks_service.actualizar(
        session, creadas["a"].id, TareaIn(titulo="Relevamiento", duracion=20, peso=50)
    )

    doc = informe_service.armar(session, proyecto.id)
    hito = next(f for f in doc.hitos if f.tarea.id == creadas["hito"].id)
    congelado = doc.desvios[creadas["hito"].id]
    assert congelado.base_fin is not None
    assert hito.fin > congelado.base_fin  # se corrió, y el informe lo puede decir


def test_el_alcance_nuevo_no_se_cuenta_como_atraso(session: Session, proyecto):
    poblar(session, proyecto)
    congelar(session, proyecto)
    agregar(session, proyecto, "Pedido extra del cliente", duracion=5)
    # Sumar alcance abre los pesos y el informe se niega a salir: hay que rebalancear,
    # que es exactamente lo que haría una persona antes de mandarlo.
    pesos_aplicar.repartir(session, proyecto.id, pesos_aplicar.PAREJO)

    doc = informe_service.armar(session, proyecto.id)
    assert [f.tarea.titulo for f in doc.nuevas] == ["Pedido extra del cliente"]
    assert doc.atrasadas == []


def test_lo_borrado_despues_de_congelar_se_reporta(session: Session, proyecto):
    creadas = poblar(session, proyecto)
    congelar(session, proyecto)
    tasks_service.eliminar(session, creadas["b"].id)
    pesos_aplicar.repartir(session, proyecto.id, pesos_aplicar.PAREJO)

    doc = informe_service.armar(session, proyecto.id)
    assert [d.titulo for d in doc.borradas] == ["Análisis"]


def test_el_cuadrante_de_riesgos_viaja_en_el_informe(session: Session, proyecto):
    poblar(session, proyecto)
    riesgos_service.crear(
        session, proyecto.id,
        RiesgoIn(descripcion="El cliente no libera el ambiente", probabilidad=5, impacto=4),
    )

    doc = informe_service.armar(session, proyecto.id)
    assert len(doc.riesgos.riesgos) == 1
    assert any(c.riesgos for fila in doc.riesgos.cuadrante for c in fila)


def test_el_gantt_del_informe_va_en_vista_de_etapas(session: Session, proyecto):
    """Un árbol completo no entra en A4."""
    poblar(session, proyecto)
    doc = informe_service.armar(session, proyecto.id)

    completo = vista_service.armar(session, proyecto.id)
    assert len(doc.filas) < len(completo.filas)
    assert all(f.nivel == 0 or f.es_hito for f in doc.filas)


# --- fecha de corte ---

def test_el_corte_mueve_el_planificado_pero_no_el_real(session: Session, proyecto):
    poblar(session, proyecto)
    congelar(session, proyecto)

    temprano = informe_service.armar(session, proyecto.id, date(2026, 1, 6))
    tarde = informe_service.armar(session, proyecto.id, date(2027, 1, 6))

    assert temprano.avance_real == tarde.avance_real
    assert temprano.avance_planificado < tarde.avance_planificado
    assert tarde.avance_planificado == 100


def test_la_brecha_dice_si_vamos_bien_o_mal(session: Session, proyecto):
    creadas = poblar(session, proyecto)
    congelar(session, proyecto)
    tasks_service.actualizar(
        session, creadas["a"].id, TareaIn(titulo="Relevamiento", duracion=10, peso=50, avance=100)
    )

    # a la fecha de arranque no debería estar hecho nada: vamos adelantados
    doc = informe_service.armar(session, proyecto.id, date(2026, 1, 5))
    assert doc.brecha > 0
