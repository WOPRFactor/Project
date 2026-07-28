from datetime import date

from sqlmodel import Session

from app.services import importar as importar_service
from app.services import importar_aplicar
from app.services import importar_texto
from app.services import schedule as schedule_service
from app.services import tasks as tasks_service

PEGADO = """
Relevamiento
    Entrevistas con el cliente   4
    Informe de brechas   2  @Ariel
Diseño
    Arquitectura objetivo   5
Hito: diseño aprobado
"""


def test_la_indentacion_arma_el_arbol():
    imp = importar_texto.leer(PEGADO)
    assert [(f.titulo, f.nivel) for f in imp.filas][:3] == [
        ("Relevamiento", 0),
        ("Entrevistas con el cliente", 1),
        ("Informe de brechas", 1),
    ]


def test_lee_duracion_y_responsable():
    imp = importar_texto.leer(PEGADO)
    por_titulo = {f.titulo: f for f in imp.filas}
    assert por_titulo["Entrevistas con el cliente"].duracion == 4
    assert por_titulo["Informe de brechas"].duracion == 2
    assert por_titulo["Informe de brechas"].responsable == "Ariel"


def test_detecta_los_hitos_por_prefijo():
    imp = importar_texto.leer(PEGADO)
    hito = [f for f in imp.filas if f.tipo == "hito"]
    assert len(hito) == 1
    assert hito[0].duracion == 0


def test_duracion_cero_tambien_es_hito():
    imp = importar_texto.leer("Firma del acta  0")
    assert imp.filas[0].tipo == "hito"


def test_acepta_tabs_y_vinetas():
    imp = importar_texto.leer("Fase\n\t- Subtarea  3\n\t\t* Sub-sub  1")
    assert [(f.titulo, f.nivel) for f in imp.filas] == [
        ("Fase", 0), ("Subtarea", 1), ("Sub-sub", 2)
    ]


def test_sin_duracion_asume_un_dia_y_avisa():
    imp = importar_texto.leer("Tarea suelta")
    assert imp.filas[0].duracion == 1
    assert any("no tenía duración" in a for a in imp.avisos)


def test_texto_vacio_no_rompe():
    imp = importar_texto.leer("   \n\n  ")
    assert imp.filas == []
    assert imp.avisos


def test_no_confunde_un_numero_del_titulo_con_la_duracion():
    imp = importar_texto.leer("Migrar 3 servidores   5")
    assert imp.filas[0].titulo == "Migrar 3 servidores"
    assert imp.filas[0].duracion == 5


def test_aplicar_crea_el_arbol(session: Session, proyecto):
    imp = importar_texto.leer(PEGADO)
    nuevo, avisos = importar_aplicar.aplicar(session, "Pegado", date(2026, 1, 5), imp)
    arbol = tasks_service.arbol(session, nuevo.id)
    assert [(t.titulo, n) for t, n in arbol][:3] == [
        ("Relevamiento", 0),
        ("Entrevistas con el cliente", 1),
        ("Informe de brechas", 1),
    ]
    assert avisos == []


def test_el_proyecto_pegado_calcula_fechas(session: Session):
    imp = importar_texto.leer(PEGADO)
    nuevo, _ = importar_aplicar.aplicar(session, "Pegado", date(2026, 1, 5), imp)
    plan, error = schedule_service.calcular_seguro(session, nuevo.id)
    assert error is None
    assert plan.inicio == date(2026, 1, 5)


def test_ida_y_vuelta_por_json_conserva_las_filas():
    imp = importar_texto.leer(PEGADO)
    vuelta = importar_service.desde_json(importar_service.a_json(imp))
    assert [f.titulo for f in vuelta.filas] == [f.titulo for f in imp.filas]
    assert [f.nivel for f in vuelta.filas] == [f.nivel for f in imp.filas]


def test_json_manipulado_se_sanea():
    manipulado = (
        '[{"titulo": "' + "A" * 500 + '", "duracion": 99999, "nivel": 999,'
        ' "tipo": "inventado", "predecesoras": "no-es-lista"}]'
    )
    vuelta = importar_service.desde_json(manipulado)
    fila = vuelta.filas[0]
    assert len(fila.titulo) == 200
    assert fila.duracion == 3650
    assert fila.nivel == 20
    assert fila.tipo == "tarea"
    assert fila.predecesoras == []


def test_json_invalido_devuelve_none():
    assert importar_service.desde_json("no soy json") is None
    assert importar_service.desde_json('{"no": "es una lista"}') is None
