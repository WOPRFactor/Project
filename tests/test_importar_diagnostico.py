"""Detección de fechas que contradicen las dependencias declaradas."""

from datetime import date
from pathlib import Path

from app.services import importar_diagnostico as diagnostico_service
from app.services import importar_excel
from app.services.importar import FilaImportada, Importacion

PLANILLA = Path(__file__).parent / "fixtures" / "gantt-traspaso.xlsx"


def fila(wbs, titulo, dias, ini, fin, pred=(), tipo="tarea"):
    return FilaImportada(
        titulo=titulo, wbs=wbs, tipo=tipo, duracion=dias, predecesoras=list(pred),
        inicio_declarado=ini, fin_declarado=fin,
    )


def test_una_planilla_coherente_no_reporta_nada():
    imp = Importacion(filas=[
        fila("1", "A", 3, date(2026, 1, 5), date(2026, 1, 7)),
        fila("2", "B", 2, date(2026, 1, 8), date(2026, 1, 9), pred=["1"]),
    ])
    assert diagnostico_service.analizar(imp).discrepancias == []


def test_detecta_inicio_a_inicio():
    imp = Importacion(filas=[
        fila("1", "Ejecución", 30, date(2026, 1, 5), date(2026, 2, 13)),
        fila("2", "Supervisión", 30, date(2026, 1, 5), date(2026, 2, 13), pred=["1"]),
    ])
    d = diagnostico_service.analizar(imp).discrepancias
    assert len(d) == 1
    assert d[0].sugerencia == "1SS"
    assert "Inicio→Inicio" in d[0].motivo


def test_detecta_fin_a_fin():
    imp = Importacion(filas=[
        fila("1", "Larga", 10, date(2026, 1, 5), date(2026, 1, 16)),
        fila("2", "Corta", 3, date(2026, 1, 14), date(2026, 1, 16), pred=["1"]),
    ])
    d = diagnostico_service.analizar(imp).discrepancias
    assert d[0].sugerencia == "1FF"


def test_detecta_un_solape():
    imp = Importacion(filas=[
        fila("1", "A", 10, date(2026, 1, 5), date(2026, 1, 16)),
        fila("2", "B", 3, date(2026, 1, 14), date(2026, 1, 19), pred=["1"]),
    ])
    d = diagnostico_service.analizar(imp).discrepancias
    assert d[0].sugerencia == "1-3"


def test_arrancar_despues_de_lo_exigido_no_es_contradiccion():
    """Fin→Inicio es un mínimo: si arranca un poco después, lo manda otra cosa."""
    imp = Importacion(filas=[
        fila("1", "A", 3, date(2026, 1, 5), date(2026, 1, 7)),
        fila("2", "B", 2, date(2026, 1, 9), date(2026, 1, 12), pred=["1"]),
    ])
    assert diagnostico_service.analizar(imp).discrepancias == []


def test_un_hueco_grande_si_se_reporta():
    imp = Importacion(filas=[
        fila("1", "A", 3, date(2026, 1, 5), date(2026, 1, 7)),
        fila("2", "B", 2, date(2026, 3, 2), date(2026, 3, 3), pred=["1"]),
    ])
    d = diagnostico_service.analizar(imp).discrepancias
    assert len(d) == 1 and "después de lo que exigen" in d[0].motivo


def test_varias_predecesoras_solo_manda_la_mas_tardia():
    imp = Importacion(filas=[
        fila("1", "A", 3, date(2026, 1, 5), date(2026, 1, 7)),
        fila("2", "B", 10, date(2026, 1, 5), date(2026, 1, 16)),
        fila("3", "C", 1, date(2026, 1, 19), date(2026, 1, 19), pred=["1", "2"]),
    ])
    assert diagnostico_service.analizar(imp).discrepancias == []


def test_aplicar_sugerencias_reescribe_las_predecesoras():
    imp = Importacion(filas=[
        fila("1", "Ejecución", 30, date(2026, 1, 5), date(2026, 2, 13)),
        fila("2", "Supervisión", 30, date(2026, 1, 5), date(2026, 2, 13), pred=["1"]),
    ])
    d = diagnostico_service.analizar(imp)
    assert diagnostico_service.aplicar_sugerencias(imp, d) == 1
    assert imp.filas[1].predecesoras == ["1SS"]
    assert diagnostico_service.analizar(imp).discrepancias == []


def test_sobre_la_planilla_real_encuentra_los_tres_ss():
    imp = importar_excel.leer(PLANILLA.read_bytes(), "Sheet2")
    d = diagnostico_service.analizar(imp)
    ss = {x.wbs: x.sugerencia for x in d.discrepancias if x.sugerencia.endswith("SS")}
    assert ss == {"4.2": "4.1SS", "4.3": "4.1SS", "4.4": "4.1SS"}


def test_sin_fechas_declaradas_no_hay_diagnostico():
    imp = Importacion(filas=[
        FilaImportada(titulo="A", wbs="1", duracion=3),
        FilaImportada(titulo="B", wbs="2", duracion=2, predecesoras=["1"]),
    ])
    assert diagnostico_service.analizar(imp).discrepancias == []


def test_las_fechas_a_mano_se_reportan_pero_no_se_aplican():
    """Fijarlas como lag congelaría el cronograma: eso lo decide una persona."""
    imp = Importacion(filas=[
        fila("1", "A", 3, date(2026, 1, 5), date(2026, 1, 7)),
        fila("2", "B", 2, date(2026, 3, 2), date(2026, 3, 3), pred=["1"]),
    ])
    d = diagnostico_service.analizar(imp)
    assert len(d.a_revisar) == 1 and d.estructurales == []
    assert diagnostico_service.aplicar_sugerencias(imp, d) == 0
    assert imp.filas[1].predecesoras == ["1"]      # intacta


def test_sobre_la_planilla_real_solo_se_aplican_las_estructurales():
    imp = importar_excel.leer(PLANILLA.read_bytes(), "Sheet2")
    d = diagnostico_service.analizar(imp)
    assert {x.sugerencia for x in d.estructurales} >= {"4.1SS"}
    assert all(x.sugerencia.endswith(("SS", "FF")) or "-" in x.sugerencia
               for x in d.estructurales)
    # ninguna corrección mete un lag positivo grande, que anclaría el cronograma
    assert not any("+1" in x.sugerencia and x.estructural for x in d.discrepancias)
