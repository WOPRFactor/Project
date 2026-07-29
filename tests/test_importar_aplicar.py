"""Aplicar un import: los datos raros avisan, nunca duplican ni abortan a medias."""

from datetime import date

from sqlmodel import Session

from app.services import importar_aplicar
from app.services import tasks as tasks_service
from app.services.importar import FilaImportada, Importacion


def test_dos_filas_con_el_mismo_wbs_avisan_y_no_duplican_el_codigo(session: Session):
    importacion = Importacion(filas=[
        FilaImportada(titulo="A", wbs="1"),
        FilaImportada(titulo="B", wbs="1"),
    ])
    proyecto, avisos = importar_aplicar.aplicar(
        session, "Duplicados", date(2026, 1, 5), importacion
    )

    codigos = [t.codigo for t in tasks_service.listar(session, proyecto.id) if t.codigo]
    assert codigos.count("1") == 1
    assert any("repetido" in a for a in avisos)


def test_un_lag_desmedido_no_aborta_el_import(session: Session):
    """`parsear` acepta hasta ±999 pero el tope real es ±365: la dependencia se
    descarta con aviso, sin dejar el proyecto a medio importar."""
    importacion = Importacion(filas=[
        FilaImportada(titulo="A", wbs="1"),
        FilaImportada(titulo="B", wbs="2", predecesoras=["1+500"]),
    ])
    proyecto, avisos = importar_aplicar.aplicar(
        session, "Lag desmedido", date(2026, 1, 5), importacion
    )

    assert len(tasks_service.listar(session, proyecto.id)) == 2
    assert any("365" in a for a in avisos)
