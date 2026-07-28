"""Pesos sobre un proyecto real: lo que se guarda, lo que se deriva y lo que se avisa."""

from sqlmodel import Session

from app.schemas import TareaIn
from app.services import arbol as arbol_service
from app.services import estados as estados_service
from app.services import pesos_aplicar
from app.services import tasks as tasks_service
from app.services import vista as vista_service


def agregar(session, proyecto, titulo, duracion=1, peso=None):
    return arbol_service.agregar_al_final(
        session, proyecto.id, TareaIn(titulo=titulo, duracion=duracion, peso=peso)
    )


def filas(session, proyecto):
    return {f.tarea.titulo: f for f in vista_service.armar(session, proyecto.id).filas}


def test_sin_pesos_declarados_el_reparto_es_parejo(session: Session, proyecto):
    agregar(session, proyecto, "A")
    agregar(session, proyecto, "B")
    assert [round(f.peso_absoluto) for f in filas(session, proyecto).values()] == [50, 50]


def test_la_etapa_reparte_su_peso_entre_las_subtareas(session: Session, proyecto):
    """El caso que pidió Ariel: etapa al 20%, cinco subtareas, cada una vale 4%."""
    etapa = agregar(session, proyecto, "Etapa", peso=20)
    agregar(session, proyecto, "Resto", peso=80)
    for i in range(5):
        hija = agregar(session, proyecto, f"Sub {i}", peso=20)
        arbol_service.indentar(session, hija.id)
        tasks_service.mover(session, hija.id, etapa.id)

    vista = filas(session, proyecto)
    assert round(vista["Etapa"].peso_absoluto) == 20
    assert [round(vista[f"Sub {i}"].peso_absoluto) for i in range(5)] == [4] * 5


def test_la_celda_guarda_el_peso_y_vacia_lo_borra(session: Session, proyecto):
    tarea = agregar(session, proyecto, "A", peso=40)
    assert tasks_service.obtener(session, tarea.id).peso == 40

    tasks_service.actualizar(session, tarea.id, TareaIn(titulo="A", peso=None))
    assert tasks_service.obtener(session, tarea.id).peso is None


def test_un_nivel_que_no_cierra_se_avisa(session: Session, proyecto):
    agregar(session, proyecto, "A", peso=40)
    agregar(session, proyecto, "B", peso=30)

    abiertos = vista_service.armar(session, proyecto.id).niveles_abiertos
    assert len(abiertos) == 1
    assert abiertos[0].diferencia == -30
    assert "faltan 30" in abiertos[0].mensaje


def test_un_nivel_que_cierra_no_molesta(session: Session, proyecto):
    agregar(session, proyecto, "A", peso=40)
    agregar(session, proyecto, "B", peso=60)
    assert vista_service.armar(session, proyecto.id).niveles_abiertos == []


def test_el_aviso_nombra_la_etapa_para_poder_encontrarla(session: Session, proyecto):
    etapa = agregar(session, proyecto, "Etapa 1")
    hija = agregar(session, proyecto, "Sub", peso=30)
    arbol_service.indentar(session, hija.id)
    tasks_service.mover(session, hija.id, etapa.id)

    abiertos = vista_service.armar(session, proyecto.id).niveles_abiertos
    assert abiertos[0].titulo == "Etapa 1"


def test_no_cerrar_no_bloquea_el_guardado(session: Session, proyecto):
    """Frenar la carga porque vas 70 mientras cargás sería infumable."""
    agregar(session, proyecto, "A", peso=70)
    vista = vista_service.armar(session, proyecto.id)
    assert vista.niveles_abiertos and vista.filas  # avisa, pero el proyecto vive


def test_un_nivel_pasado_de_100_no_da_un_avance_imposible(session: Session, proyecto):
    hecha = estados_service.final(session, proyecto.id)
    a = agregar(session, proyecto, "A", peso=80)
    b = agregar(session, proyecto, "B", peso=80)
    tasks_service.cambiar_estado(session, a.id, hecha.id)
    tasks_service.cambiar_estado(session, b.id, hecha.id)

    assert vista_service.armar(session, proyecto.id).avance_ponderado == 100


# --- avance ponderado ---

def test_el_avance_pesa_por_valor_y_no_por_cantidad(session: Session, proyecto):
    hecha = estados_service.final(session, proyecto.id)
    firma = agregar(session, proyecto, "Firma del acta", duracion=1, peso=90)
    agregar(session, proyecto, "Acompañamiento", duracion=120, peso=10)
    tasks_service.cambiar_estado(session, firma.id, hecha.id)

    vista = vista_service.armar(session, proyecto.id)
    assert vista.avance_ponderado == 90     # ponderado: lo que vale
    assert vista.resumen.avance == 50       # por cabezas: una de dos


def test_un_estado_intermedio_aporta_su_avance_sugerido(session: Session, proyecto):
    en_curso = [e for e in estados_service.listar(session, proyecto.id) if e.nombre == "En curso"][0]
    a = agregar(session, proyecto, "A", peso=100)
    tasks_service.cambiar_estado(session, a.id, en_curso.id)

    assert vista_service.armar(session, proyecto.id).avance_ponderado == en_curso.avance_sugerido


# --- puntos de partida ---

def test_repartir_por_duracion_le_da_mas_a_la_mas_larga(session: Session, proyecto):
    agregar(session, proyecto, "Corta", duracion=10)
    agregar(session, proyecto, "Larga", duracion=30)

    pesos_aplicar.repartir(session, proyecto.id, pesos_aplicar.POR_DURACION)

    vista = filas(session, proyecto)
    assert vista["Corta"].tarea.peso == 25 and vista["Larga"].tarea.peso == 75


def test_repartir_parejo_cierra_aunque_no_sea_divisible(session: Session, proyecto):
    for nombre in "ABC":
        agregar(session, proyecto, nombre)

    pesos_aplicar.repartir(session, proyecto.id, pesos_aplicar.PAREJO)

    vista = vista_service.armar(session, proyecto.id)
    assert sum(f.tarea.peso for f in vista.filas) == 100
    assert vista.niveles_abiertos == []


def test_limpiar_vuelve_al_reparto_automatico(session: Session, proyecto):
    agregar(session, proyecto, "A", peso=90)
    agregar(session, proyecto, "B", peso=10)

    pesos_aplicar.limpiar(session, proyecto.id)

    vista = filas(session, proyecto)
    assert all(f.tarea.peso is None for f in vista.values())
    assert [round(f.peso_absoluto) for f in vista.values()] == [50, 50]


def test_repartir_toca_cada_nivel_por_separado(session: Session, proyecto):
    etapa = agregar(session, proyecto, "Etapa")
    for nombre in ("Sub 1", "Sub 2"):
        hija = agregar(session, proyecto, nombre)
        arbol_service.indentar(session, hija.id)
        tasks_service.mover(session, hija.id, etapa.id)

    pesos_aplicar.repartir(session, proyecto.id, pesos_aplicar.PAREJO)

    vista = filas(session, proyecto)
    assert vista["Etapa"].tarea.peso == 100
    assert vista["Sub 1"].tarea.peso == 50 and vista["Sub 2"].tarea.peso == 50
    assert round(vista["Sub 1"].peso_absoluto) == 50


# --- el filtro de la vista no toca los números de arriba ---

def test_filtrar_la_vista_no_cambia_los_totales(session: Session, proyecto):
    """Un Gantt filtrado que además cambiara los totales es una captura engañosa."""
    from app.services.gantt_vista import ETAPAS, Mirada

    etapa = agregar(session, proyecto, "Etapa", duracion=1)
    hija = agregar(session, proyecto, "Sub", duracion=10)
    arbol_service.indentar(session, hija.id)
    tasks_service.mover(session, hija.id, etapa.id)

    completa = vista_service.armar(session, proyecto.id)
    filtrada = vista_service.armar(session, proyecto.id, mirada=Mirada(detalle=ETAPAS))

    assert len(filtrada.filas) < len(completa.filas)
    assert filtrada.resumen.dias_habiles == completa.resumen.dias_habiles
    assert filtrada.resumen.fin == completa.resumen.fin
    assert filtrada.avance_ponderado == completa.avance_ponderado
    assert len(filtrada.todas_las_filas) == len(completa.filas)


def test_el_cronograma_se_calcula_entero_aunque_se_filtre(session: Session, proyecto):
    """Si el filtro sacara tareas del cálculo, las dependencias darían otras fechas."""
    from app.services import predecesoras as predecesoras_service
    from app.services.gantt_vista import ETAPAS, Mirada

    a = agregar(session, proyecto, "A", duracion=5)
    b = agregar(session, proyecto, "B", duracion=5)
    predecesoras_service.guardar(session, proyecto.id, b.id, a.codigo)

    sin_filtro = vista_service.armar(session, proyecto.id).resumen.fin
    con_filtro = vista_service.armar(
        session, proyecto.id, mirada=Mirada(detalle=ETAPAS)
    ).resumen.fin
    assert sin_filtro == con_filtro
