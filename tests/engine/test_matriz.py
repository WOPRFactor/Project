"""Matriz de riesgo 5×5. Módulo puro: ni base ni sesión."""

from app.services.matriz import Zona, acotar, cuadrante, por_zona, severidad, zona


def test_la_severidad_es_el_producto():
    assert severidad(4, 5) == 20


def test_la_escala_se_recorta_en_vez_de_explotar():
    assert acotar(0) == 1 and acotar(9) == 5
    assert severidad(0, 99) == 5


# --- los cuatro bordes de zona ---

def test_borde_bajo_medio():
    assert zona(4) is Zona.bajo
    assert zona(5) is Zona.medio


def test_borde_medio_alto():
    assert zona(9) is Zona.medio
    assert zona(10) is Zona.alto


def test_borde_alto_critico():
    assert zona(14) is Zona.alto
    assert zona(15) is Zona.critico


def test_el_maximo_es_critico():
    assert zona(severidad(5, 5)) is Zona.critico


def test_el_minimo_es_bajo():
    assert zona(severidad(1, 1)) is Zona.bajo


# --- armado del cuadrante ---

def test_el_cuadrante_es_de_cinco_por_cinco():
    grilla = cuadrante([])
    assert len(grilla) == 5 and all(len(fila) == 5 for fila in grilla)


def test_se_lee_con_lo_peor_arriba_a_la_derecha():
    grilla = cuadrante([])
    assert grilla[0][0].probabilidad == 5 and grilla[0][0].impacto == 1
    assert grilla[0][-1].severidad == 25   # arriba a la derecha: lo peor
    assert grilla[-1][0].severidad == 1    # abajo a la izquierda: lo más leve


def test_cada_riesgo_cae_en_su_casilla():
    grilla = cuadrante([(7, 4, 5)])
    ubicado = [c for fila in grilla for c in fila if c.riesgos]
    assert len(ubicado) == 1
    assert ubicado[0].probabilidad == 4 and ubicado[0].impacto == 5
    assert ubicado[0].riesgos == (7,)


def test_dos_riesgos_en_la_misma_casilla_se_apilan():
    grilla = cuadrante([(1, 3, 3), (2, 3, 3)])
    celda = [c for fila in grilla for c in fila if c.riesgos][0]
    assert celda.cuantos == 2


def test_un_riesgo_fuera_de_escala_no_se_pierde():
    grilla = cuadrante([(1, 99, -3)])
    celda = [c for fila in grilla for c in fila if c.riesgos][0]
    assert celda.probabilidad == 5 and celda.impacto == 1


def test_el_conteo_por_zona_cubre_las_cuatro():
    conteo = por_zona([(1, 1, 1), (2, 2, 3), (3, 3, 4), (4, 5, 5)])
    assert conteo == {Zona.bajo: 1, Zona.medio: 1, Zona.alto: 1, Zona.critico: 1}


def test_sin_riesgos_todas_las_zonas_estan_en_cero():
    assert set(por_zona([]).values()) == {0}
