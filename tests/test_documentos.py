"""Fase 30: el plan y el informe como PDF y como Word.

Lo que se cuida acá no es que la descarga «ande», sino que **el documento no salga
mutilado**: que el Gantt entre en el ancho de la hoja (Chrome corta lo que sobra sin
avisar), que el Word tenga de verdad las tareas adentro, y que sin Chrome el usuario vea
un mensaje y no un stack trace.

El PDF necesita Chrome instalado, así que esos tests se saltean solos donde no esté —
igual que los de navegador. Los del Word y los del cálculo del ancho corren siempre.
"""

from datetime import date

import pytest
from docx import Document
from sqlmodel import Session

from app.services import documento as documento_service
from app.services import exportar_docx, exportar_pdf
from app.services import informe as informe_service
from app.services.documento import DocumentoInvalido

from .test_app import (  # noqa: F401
    celda, cliente_anonimo_fixture, cliente_fixture, crear_proyecto,
)

sin_chrome = pytest.mark.skipif(
    not exportar_pdf.hay_como_imprimir(),
    reason="el PDF lo imprime el Chrome del sistema; acá no hay ninguno",
)


@pytest.fixture(name="proyecto_con_tareas")
def proyecto_con_tareas_fixture(cliente):  # noqa: F811
    """Un proyecto chico pero completo: etapa con subtareas, dependencia e hito."""
    crear_proyecto(cliente)
    for _ in range(4):
        cliente.post("/proyectos/1/tareas/agregar")
    celda(cliente, 1, codigo="1", titulo="Etapa de arranque")
    celda(cliente, 2, codigo="1.1", titulo="Relevamiento", duracion=5)
    cliente.post("/proyectos/1/tareas/2/indentar")
    celda(cliente, 3, codigo="1.2", titulo="Informe técnico", duracion=3, predecesoras="1.1")
    cliente.post("/proyectos/1/tareas/3/indentar")
    celda(cliente, 4, codigo="2", titulo="Hito: arranque cerrado", duracion=0)
    return cliente


# ---------------------------------------------------------------- el ancho de la hoja

def test_el_gantt_se_comprime_para_entrar_en_la_hoja():
    """Un año de proyecto a 22px por día son 5000px de timeline: Chrome corta lo que no
    entra, así que el documento tiene que angostar el día, no perder los últimos meses."""
    assert documento_service.ancho_de_dia(20, 700) == documento_service.ANCHO_DIA_MAXIMO
    ancho = documento_service.ancho_de_dia(415, 700)
    assert ancho < documento_service.ANCHO_COMPRIMIDO
    assert 415 * ancho <= 700
    # Y usa la hoja entera: truncar a 1px desperdiciaba el 40% del ancho.
    assert 415 * ancho > 700 * 0.95


def test_el_ancho_de_dia_nunca_baja_de_un_pixel():
    """Con un proyecto absurdamente largo, mejor comprimido al mínimo que invisible."""
    assert documento_service.ancho_de_dia(5000, 700) == 1.0


def test_sin_columnas_no_divide_por_cero():
    assert documento_service.ancho_de_dia(0, 700) == documento_service.ANCHO_DIA_MAXIMO


# ---------------------------------------------------------------------------- el plan

def test_el_plan_sale_completo_y_no_depende_de_la_vista(proyecto_con_tareas, session):
    """El documento lleva **todas** las tareas: si dependiera de las etapas plegadas en
    pantalla, el PDF que mandás por mail cambiaría según cómo dejaste tu sesión."""
    from app.db import get_session
    from app.main import app

    generador = app.dependency_overrides[get_session]()
    sesion = next(generador)
    plan = documento_service.armar(sesion, 1)

    assert len(plan.filas) == 4
    assert [f.tarea.codigo for f in plan.filas] == ["1", "1.1", "1.2", "2"]
    assert plan.resumen.fin is not None
    assert plan.titulo_panel == "Tarea"


def test_el_plan_avisa_de_los_pesos_abiertos_pero_se_emite(proyecto_con_tareas):
    """A diferencia del informe, el plan no se niega: negarle a alguien el plan de obra
    porque los pesos no suman 100 sería absurdo. Avisa y sigue."""
    from app.db import get_session
    from app.main import app

    sesion = next(app.dependency_overrides[get_session]())
    celda(proyecto_con_tareas, 2, codigo="1.1", titulo="Relevamiento", duracion=5, peso=100)
    celda(proyecto_con_tareas, 3, codigo="1.2", titulo="Informe técnico", duracion=3, peso=60)

    plan = documento_service.armar(sesion, 1)
    assert plan.avisos, "los pesos pasados de 100 tienen que avisarse en el documento"
    assert plan.filas, "y el plan tiene que salir igual"


def test_un_proyecto_sin_tareas_no_genera_un_documento_vacio(cliente):  # noqa: F811
    from app.db import get_session
    from app.main import app

    crear_proyecto(cliente)
    sesion = next(app.dependency_overrides[get_session]())
    with pytest.raises(DocumentoInvalido, match="no tiene tareas"):
        documento_service.armar(sesion, 1)


# ----------------------------------------------------------------------------- el Word

def test_el_plan_en_word_trae_las_tareas(proyecto_con_tareas, tmp_path):
    from app.db import get_session
    from app.main import app

    sesion = next(app.dependency_overrides[get_session]())
    cuerpo = exportar_docx.del_plan(documento_service.armar(sesion, 1))

    archivo = tmp_path / "plan.docx"
    archivo.write_bytes(cuerpo)
    # Se relee con python-docx: que Word lo pueda abrir, no solo que no explote al crearlo.
    doc = Document(str(archivo))
    texto = "\n".join(p.text for p in doc.paragraphs)
    assert "Plan de trabajo al" in texto

    tabla = doc.tables[-1]
    assert len(tabla.rows) == 5  # encabezado + 4 tareas
    celdas = "\n".join(c.text for f in tabla.rows for c in f.cells)
    for esperado in ("Relevamiento", "Informe técnico", "Hito: arranque cerrado", "1.2"):
        assert esperado in celdas


def test_el_word_del_plan_sale_apaisado(proyecto_con_tareas, tmp_path):
    """Once columnas no entran en una hoja vertical."""
    from app.db import get_session
    from app.main import app

    sesion = next(app.dependency_overrides[get_session]())
    archivo = tmp_path / "plan.docx"
    archivo.write_bytes(exportar_docx.del_plan(documento_service.armar(sesion, 1)))

    seccion = Document(str(archivo)).sections[0]
    assert seccion.page_width > seccion.page_height


# ------------------------------------------------------------------------ las descargas

def test_las_cuatro_descargas_responden(proyecto_con_tareas):
    cliente = proyecto_con_tareas
    docx_plan = cliente.get("/proyectos/1/export/plan.docx")
    assert docx_plan.status_code == 200
    assert docx_plan.content[:2] == b"PK"  # un .docx es un zip
    assert "plan-mudanza.docx" in docx_plan.headers["content-disposition"]

    if exportar_pdf.hay_como_imprimir():
        pdf_plan = cliente.get("/proyectos/1/export/plan.pdf")
        assert pdf_plan.status_code == 200
        assert pdf_plan.content[:4] == b"%PDF"
        assert "plan-mudanza.pdf" in pdf_plan.headers["content-disposition"]

    # El informe exige pesos cerrados; con los pesos automáticos de este proyecto cierra.
    informe = cliente.get("/proyectos/1/export/informe.docx")
    assert informe.status_code == 200
    assert informe.content[:2] == b"PK"


def test_el_informe_que_no_se_puede_emitir_avisa_en_castellano(proyecto_con_tareas):
    """Pesos abiertos: el informe se niega. Tiene que decirlo, no tirar un 500."""
    cliente = proyecto_con_tareas
    celda(cliente, 2, codigo="1.1", titulo="Relevamiento", duracion=5, peso=100)
    celda(cliente, 3, codigo="1.2", titulo="Informe técnico", duracion=3, peso=60)

    respuesta = cliente.get("/proyectos/1/export/informe.docx")
    assert respuesta.status_code == 400
    assert "pesos" in respuesta.text.lower()


def test_un_corte_invalido_no_rompe_la_descarga(proyecto_con_tareas):
    respuesta = proyecto_con_tareas.get(
        "/proyectos/1/export/informe.docx?corte=el-jueves"
    )
    assert respuesta.status_code == 200


def test_el_ajeno_no_se_lleva_los_documentos(cliente_anonimo):  # noqa: F811
    """Son rutas de lectura, pero de un proyecto: sin sesión no se descargan."""
    for ruta in ("plan.pdf", "plan.docx", "informe.pdf", "informe.docx"):
        respuesta = cliente_anonimo.get(f"/proyectos/1/export/{ruta}")
        assert respuesta.status_code in (303, 404), ruta


# -------------------------------------------------------------------------------- PDF

@sin_chrome
def test_el_pdf_es_un_pdf_de_verdad():
    cuerpo = exportar_pdf.desde_html("<h1>Hola</h1>")
    assert cuerpo[:4] == b"%PDF"
    assert len(cuerpo) > 500


def test_sin_navegador_el_mensaje_es_claro(monkeypatch):
    """Lo que ve alguien sin Chrome: una explicación, no una excepción de subprocess."""
    monkeypatch.setattr(exportar_pdf, "navegador", lambda: None)
    with pytest.raises(exportar_pdf.PdfNoDisponible, match="Chrome"):
        exportar_pdf.desde_html("<h1>Hola</h1>")


def test_el_informe_en_pdf_comprime_su_gantt():
    """El informe va en hoja vertical, que es más angosta: se ajusta aparte del plan."""
    falso = informe_service.Informe(proyecto=None, corte=date(2026, 1, 5))
    falso.grilla = type("G", (), {"columnas": 415})()
    documento_service.ajustar_al_papel(falso, horizontal=False)

    assert falso.comprimido
    assert 415 * falso.ancho_dia <= documento_service.ANCHO_TIMELINE_VERTICAL
