"""Congelar el cronograma y medir cuánto se movió desde entonces.

La aritmética vive en `engine/comparar.py` y no toca la base. Acá se lee, se
escribe, y se traduce entre modelos y las dataclasses del motor.

Una regla que se cuida acá: **no se congela con los pesos abiertos.** Durante la
carga que un nivel no dé 100 es normal y solo se avisa; pero una línea base es lo
que se le promete a alguien, y prometer con una cuenta que no cierra convierte todo
avance posterior en un número inventado.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from ..engine import comparar as comparar_engine
from ..models_base import LineaBase, LineaBaseTarea


class LineaBaseInvalida(Exception):
    """Congelado rechazado; el mensaje se le muestra al usuario."""


def listar(session: Session, project_id: int) -> list[LineaBase]:
    lineas = list(session.exec(select(LineaBase).where(LineaBase.project_id == project_id)))
    lineas.sort(key=lambda l: (l.congelada_el, l.id or 0), reverse=True)
    return lineas


def vigente(session: Session, project_id: int) -> LineaBase | None:
    return next((l for l in listar(session, project_id) if l.vigente), None)


def tareas_de(session: Session, linea_base_id: int) -> list[LineaBaseTarea]:
    return list(session.exec(
        select(LineaBaseTarea).where(LineaBaseTarea.linea_base_id == linea_base_id)
    ))


def congelar(
    session: Session, project_id: int, datos, nombre: str,
    nota: str = "", hoy: date | None = None,
) -> LineaBase:
    """Guarda el cronograma de este momento como la nueva línea base vigente.

    Recibe la vista ya armada en vez de construirla: evita el ciclo de imports con
    `vista.py` y de paso no recalcula el cronograma dos veces por pantalla.
    """
    if datos.error:
        raise LineaBaseInvalida(
            f"El cronograma no se puede calcular ({datos.error}): arreglá eso antes de congelar"
        )
    if not datos.todas_las_filas:
        raise LineaBaseInvalida("El proyecto no tiene tareas para congelar")
    if datos.niveles_abiertos:
        detalle = "; ".join(n.mensaje for n in datos.niveles_abiertos)
        raise LineaBaseInvalida(
            "Los pesos no cierran, así que el avance contra esta base no significaría "
            f"nada. Cerralos primero — {detalle}"
        )

    for anterior in listar(session, project_id):
        if anterior.vigente:
            anterior.vigente = False
            session.add(anterior)

    linea = LineaBase(
        project_id=project_id,
        nombre=nombre.strip()[:80] or f"Base {(hoy or date.today()).isoformat()}",
        congelada_el=hoy or date.today(),
        nota=nota.strip()[:500],
        vigente=True,
    )
    session.add(linea)
    session.commit()
    session.refresh(linea)

    for fila in datos.todas_las_filas:
        session.add(LineaBaseTarea(
            linea_base_id=linea.id or 0,
            task_id=fila.tarea.id or 0,
            codigo=fila.tarea.codigo,
            titulo=fila.tarea.titulo,
            inicio=fila.inicio,
            fin=fila.fin,
            duracion=fila.tarea.duracion,
            ambito=fila.tarea.ambito.value,
            peso_absoluto=fila.peso_absoluto,
        ))
    session.commit()
    return linea


def marcar_vigente(session: Session, project_id: int, linea_base_id: int) -> None:
    for linea in listar(session, project_id):
        linea.vigente = linea.id == linea_base_id
        session.add(linea)
    session.commit()


def eliminar(session: Session, linea_base_id: int) -> None:
    for tarea in tareas_de(session, linea_base_id):
        session.delete(tarea)
    linea = session.get(LineaBase, linea_base_id)
    if linea is not None:
        session.delete(linea)
    session.commit()


def eliminar_del_proyecto(session: Session, project_id: int) -> None:
    for linea in listar(session, project_id):
        for tarea in tareas_de(session, linea.id or 0):
            session.delete(tarea)
        session.delete(linea)


def fechas_base(session: Session, project_id: int) -> dict[int, tuple]:
    """`{task_id: (inicio, fin)}` de la base vigente, o vacío si no hay.

    Se devuelve como dato plano a propósito: así `vista.py` calcula el desvío de
    cada fila sin importar este módulo, que a su vez necesita la vista.
    """
    linea = vigente(session, project_id)
    if linea is None:
        return {}
    return {t.task_id: (t.inicio, t.fin) for t in tareas_de(session, linea.id or 0)}


def desvios(session: Session, project_id: int, datos) -> dict[int, comparar_engine.Desvio]:
    """Desvío por tarea contra la base vigente. Sin base vigente, diccionario vacío."""
    linea = vigente(session, project_id)
    if linea is None:
        return {}
    resultado = comparar_engine.comparar(
        _congeladas(tareas_de(session, linea.id or 0)), _actuales(datos),
    )
    return {d.task_id: d for d in resultado}


def desvio_por_ambito(session: Session, project_id: int, datos) -> dict[str, int]:
    linea = vigente(session, project_id)
    if linea is None:
        return {}
    return comparar_engine.por_ambito(
        _congeladas(tareas_de(session, linea.id or 0)), _actuales(datos),
    )


def avance_planificado(session: Session, project_id: int, corte: date | None = None) -> int | None:
    """Cuánto debería estar hecho hoy según la base vigente. Sin base, `None`."""
    linea = vigente(session, project_id)
    if linea is None:
        return None
    return comparar_engine.avance_planificado(
        _congeladas(tareas_de(session, linea.id or 0)), corte or date.today(),
    )


def _congeladas(tareas: list[LineaBaseTarea]) -> list[comparar_engine.Congelada]:
    return [
        comparar_engine.Congelada(
            task_id=t.task_id, titulo=t.titulo, inicio=t.inicio,
            fin=t.fin, duracion=t.duracion, ambito=t.ambito,
            peso_absoluto=t.peso_absoluto,
        )
        for t in tareas
    ]


def _actuales(datos) -> list[comparar_engine.Congelada]:
    return [
        comparar_engine.Congelada(
            task_id=f.tarea.id or 0, titulo=f.tarea.titulo, inicio=f.inicio,
            fin=f.fin, duracion=f.tarea.duracion, ambito=f.tarea.ambito.value,
        )
        for f in datos.todas_las_filas
    ]
