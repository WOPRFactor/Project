"""Qué se ve del Gantt y de qué color. Módulo puro: se arman Filas a mano, sin DB."""

from app.models import Ambito, ColorEstado, Estado, Task
from app.services.gantt_vista import (
    ETAPAS,
    POR_AMBITO,
    POR_AVANCE,
    POR_CRITICIDAD,
    POR_ESTADO,
    TODO,
    Mirada,
    avance,
    clase_color,
    etapas,
    filtrar,
)
from app.services.vista import Fila


def estado(nombre="Pendiente", color=ColorEstado.gris, final=False, sugerido=0):
    return Estado(
        id=1, project_id=1, nombre=nombre, color=color,
        es_final=final, avance_sugerido=sugerido,
    )


def fila(id_, nivel=0, parent=None, resumen=False, hito=False, critica=False,
         ambito=Ambito.proyecto, est=None, avance_real=0):
    tarea = Task(
        id=id_, project_id=1, parent_id=parent, titulo=f"T{id_}",
        critica=critica, ambito=ambito, avance=avance_real,
    )
    return Fila(tarea=tarea, nivel=nivel, es_resumen=resumen, es_hito=hito, estado=est)


ARBOL = [
    fila(1, nivel=0, resumen=True),
    fila(2, nivel=1, parent=1),
    fila(3, nivel=1, parent=1, hito=True),
    fila(4, nivel=2, parent=2),
    fila(5, nivel=0),
]


# --- filtros ---

def test_por_defecto_se_ve_todo():
    assert len(filtrar(ARBOL, Mirada())) == 5


def test_solo_etapas_deja_el_nivel_cero_y_los_hitos():
    """Los hitos son lo que se reporta: esconderlos dejaría la vista sin marcas."""
    visibles = filtrar(ARBOL, Mirada(detalle=ETAPAS))
    assert {f.tarea.id for f in visibles} == {1, 3, 5}


def test_hasta_nivel_recorta_la_profundidad():
    visibles = filtrar(ARBOL, Mirada(detalle="n1"))
    assert {f.tarea.id for f in visibles} == {1, 2, 3, 5}


def test_filtrar_por_etapa_trae_la_rama_entera():
    visibles = filtrar(ARBOL, Mirada(etapa=1))
    assert {f.tarea.id for f in visibles} == {1, 2, 3, 4}


def test_una_etapa_sin_hijas_se_muestra_sola():
    assert {f.tarea.id for f in filtrar(ARBOL, Mirada(etapa=5))} == {5}


def test_etapa_y_detalle_se_combinan():
    visibles = filtrar(ARBOL, Mirada(detalle=ETAPAS, etapa=1))
    assert {f.tarea.id for f in visibles} == {1, 3}


def test_una_etapa_inexistente_no_rompe():
    assert filtrar(ARBOL, Mirada(etapa=999)) == []


def test_saber_si_esta_filtrada():
    assert not Mirada().filtrada
    assert Mirada(detalle=ETAPAS).filtrada
    assert Mirada(etapa=1).filtrada
    assert not Mirada(color=POR_ESTADO).filtrada  # el color no filtra nada


def test_las_etapas_del_selector_son_las_de_la_raiz():
    assert {f.tarea.id for f in etapas(ARBOL)} == {1, 5}


# --- lo que llega del formulario no se toma como viene ---

def test_un_detalle_invalido_cae_en_todo():
    assert Mirada(detalle="'; DROP TABLE").normalizada().detalle == TODO


def test_un_color_invalido_cae_en_criticidad():
    assert Mirada(color="rgb(0,0,0)").normalizada().color == POR_CRITICIDAD


# --- colores ---

def test_el_resumen_no_se_pinta():
    """Una barra de resumen es una envolvente, no trabajo: no tiene estado propio."""
    assert clase_color(fila(1, resumen=True, est=estado()), POR_ESTADO) == "resumen"


def test_por_criticidad_solo_grita_la_que_marcó_el_usuario():
    assert clase_color(fila(1, critica=True), POR_CRITICIDAD) == "critica"
    assert clase_color(fila(2), POR_CRITICIDAD) == "color-azul"


def test_por_estado_toma_el_color_del_estado():
    verde = estado(color=ColorEstado.verde)
    assert clase_color(fila(1, est=verde), POR_ESTADO) == "color-verde"


def test_por_estado_sin_estado_no_rompe():
    assert clase_color(fila(1), POR_ESTADO) == "color-gris"


def test_por_ambito_distingue_los_tres():
    assert clase_color(fila(1, ambito=Ambito.seguimiento), POR_AMBITO) == "ambito-barra-seguimiento"
    assert clase_color(fila(2, ambito=Ambito.control), POR_AMBITO) == "ambito-barra-control"


def test_por_avance_recorre_los_cuatro_tramos():
    def color(real):
        return clase_color(fila(1, avance_real=real), POR_AVANCE)

    assert color(0) == "color-gris"
    assert color(30) == "color-ambar"
    assert color(50) == "color-azul"
    assert color(100) == "color-verde"


def test_el_avance_pintado_es_el_real_de_la_tarea():
    """No el sugerido por el estado: el estado sugiere, la tarea manda."""
    assert avance(fila(1, est=estado(sugerido=100), avance_real=40)) == 40
    assert avance(fila(1)) == 0


# --- columnas visibles ---

def test_por_defecto_no_estan_todas_prendidas():
    """Con las trece la grilla mide más de 1400px y deja el timeline sin lugar."""
    from app.services.gantt_vista import COLUMNAS, COLUMNAS_POR_DEFECTO

    assert COLUMNAS_POR_DEFECTO < set(COLUMNAS)
    assert "resp" in COLUMNAS_POR_DEFECTO and "fin" in COLUMNAS_POR_DEFECTO


def test_sin_parametro_se_usan_las_de_por_defecto():
    from app.services.gantt_vista import COLUMNAS_POR_DEFECTO, leer_columnas

    assert leer_columnas(None) == COLUMNAS_POR_DEFECTO


def test_lista_vacia_es_una_eleccion_valida():
    """Dejar solo WBS y Tarea es legítimo; no es lo mismo que no haber elegido."""
    from app.services.gantt_vista import leer_columnas

    assert leer_columnas([]) == frozenset()


def test_acepta_checkboxes_repetidos():
    from app.services.gantt_vista import leer_columnas

    assert leer_columnas(["resp", "dias"]) == frozenset({"resp", "dias"})


def test_acepta_la_forma_separada_por_coma_del_hx_vals():
    from app.services.gantt_vista import leer_columnas

    assert leer_columnas(["resp,dias,fin"]) == frozenset({"resp", "dias", "fin"})


def test_una_columna_inventada_se_descarta():
    from app.services.gantt_vista import leer_columnas

    assert leer_columnas(["resp", "'; DROP TABLE"]) == frozenset({"resp"})


def test_la_mirada_sabe_que_columna_mostrar():
    from app.services.gantt_vista import Mirada

    mirada = Mirada(columnas=frozenset({"dias"}))
    assert mirada.ve("dias") and not mirada.ve("peso")


def test_las_columnas_viajan_y_vuelven_igual():
    from app.services.gantt_vista import Mirada, leer_columnas

    original = Mirada(columnas=frozenset({"fin", "dias", "resp"}))
    assert leer_columnas([original.columnas_texto]) == original.columnas


# --- ancho de la columna Tarea ---

def test_sin_filas_el_ancho_es_el_minimo():
    from app.services.gantt_vista import ancho_tarea

    assert ancho_tarea([]) == 260


def test_un_titulo_largo_ensancha_la_columna():
    from app.services.gantt_vista import ancho_tarea

    corto = ancho_tarea([_con_titulo("A")])
    largo = ancho_tarea([_con_titulo("Incorporación de Líder + 4 Especialistas Técnicos")])
    assert largo > corto == 260


def test_el_ancho_tiene_techo():
    """Es solo el punto de partida: después la columna se estira o se encoge con el
    espacio que sobre en el panel. Sin tope, un título kilométrico pediría un ancho
    absurdo y el resto de las columnas arrancarían aplastadas."""
    from app.services.gantt_vista import COLUMNAS, ancho_tarea

    assert ancho_tarea([_con_titulo("x" * 400)]) == 620
    assert "tarea" not in COLUMNAS  # no se puede apagar


def test_la_sangria_cuenta_para_el_ancho():
    """Una subtarea arranca corrida a la derecha: su título necesita más lugar."""
    from app.services.gantt_vista import ancho_tarea

    titulo = "Validación y firma formal de la Matriz RACI"  # largo para pasar el mínimo
    llano = ancho_tarea([_con_titulo(titulo, nivel=0)])
    hondo = ancho_tarea([_con_titulo(titulo, nivel=3)])
    assert hondo > llano


def _con_titulo(titulo, nivel=0):
    from app.models import Task

    from app.services.vista import Fila

    return Fila(tarea=Task(id=1, project_id=1, titulo=titulo), nivel=nivel, es_resumen=False)
