"""Escribe en la base lo que se importó: crea las tareas y las vincula.

Separado de `importar.py` a propósito: allá se describe qué entraría, acá se
escribe. Cada dependencia se valida contra el motor antes de guardarse.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Session

from ..models import Project
from ..schemas import DependenciaIn, ProyectoIn, TareaIn
from . import dependencies as dependencies_service
from . import projects as projects_service
from . import tasks as tasks_service
from . import predecesoras as predecesoras_service
from .importar import FilaImportada, Importacion
from .tasks import TareaInvalida


def aplicar(
    session: Session,
    nombre: str,
    fecha_inicio: date,
    importacion: Importacion,
) -> tuple[Project, list[str]]:
    """Crea el proyecto con sus tareas y dependencias. Devuelve los avisos del alta."""
    proyecto = projects_service.crear(
        session, ProyectoIn(nombre=nombre, fecha_inicio=fecha_inicio)
    )
    avisos: list[str] = []
    por_wbs: dict[str, int] = {}
    ultimo_por_nivel: dict[int, int] = {}

    for fila in importacion.filas:
        padre_id = _padre_de(fila, por_wbs, ultimo_por_nivel, avisos)
        tarea = tasks_service.crear(
            session,
            proyecto.id,
            TareaIn(
                titulo=fila.titulo[:200],
                responsable=fila.responsable[:120],
                critica=fila.critica,
                duracion=0 if fila.es_hito else max(fila.duracion, 1),
                parent_id=padre_id,
            ),
        )
        if fila.wbs:
            # El WBS de la planilla pasa a ser el código con el que se escriben
            # las dependencias en la grilla.
            tarea.codigo = fila.wbs[:40]
            session.add(tarea)
            session.commit()
            session.refresh(tarea)
            por_wbs[fila.wbs] = tarea.id
        ultimo_por_nivel[fila.nivel] = tarea.id
        for mas_hondo in [n for n in ultimo_por_nivel if n > fila.nivel]:
            del ultimo_por_nivel[mas_hondo]

    avisos += _vincular(session, proyecto.id, importacion.filas, por_wbs)
    return proyecto, avisos


def agregar_a_proyecto(
    session: Session, project_id: int, importacion: Importacion
) -> list[str]:
    """Suma las filas importadas al final de un proyecto que ya existe.

    A diferencia de crear uno nuevo, acá los códigos pueden chocar con los que ya
    hay: en ese caso la fila entra con un código libre y queda avisado, porque un
    código repetido haría que una dependencia apunte a la tarea equivocada.
    """
    from . import arbol as arbol_service

    avisos: list[str] = []
    ocupados = {t.codigo for t in tasks_service.listar(session, project_id) if t.codigo}
    por_wbs: dict[str, int] = {}
    ultimo_por_nivel: dict[int, int] = {}

    for fila in importacion.filas:
        padre_id = _padre_al_agregar(fila, por_wbs, ultimo_por_nivel)
        tarea = arbol_service.agregar_al_final(
            session,
            project_id,
            TareaIn(
                titulo=fila.titulo[:200],
                responsable=fila.responsable[:120],
                critica=fila.critica,
                duracion=0 if fila.es_hito else max(fila.duracion, 1),
                parent_id=padre_id,
            ),
        )
        if fila.wbs:
            if fila.wbs in ocupados:
                avisos.append(
                    f"El código {fila.wbs} ya estaba usado en este proyecto: "
                    f"«{fila.titulo[:40]}» entró como {tarea.codigo}"
                )
            else:
                tarea.codigo = fila.wbs[:40]
                session.add(tarea)
                session.commit()
                session.refresh(tarea)
            ocupados.add(tarea.codigo)
            por_wbs[fila.wbs] = tarea.id

        ultimo_por_nivel[fila.nivel] = tarea.id
        for mas_hondo in [n for n in ultimo_por_nivel if n > fila.nivel]:
            del ultimo_por_nivel[mas_hondo]

    avisos += _vincular(session, project_id, importacion.filas, por_wbs)
    return avisos + importacion.avisos


def _padre_al_agregar(
    fila: FilaImportada, por_wbs: dict[str, int], ultimo_por_nivel: dict[int, int]
) -> int | None:
    """El WBS manda si está; si no, la indentación del nivel."""
    if fila.wbs and "." in fila.wbs:
        padre = por_wbs.get(fila.wbs.rsplit(".", 1)[0])
        if padre is not None:
            return padre
    return ultimo_por_nivel.get(fila.nivel - 1) if fila.nivel else None


def _padre_de(
    fila: FilaImportada,
    por_wbs: dict[str, int],
    ultimo_por_nivel: dict[int, int],
    avisos: list[str],
) -> int | None:
    if fila.nivel == 0:
        return None
    if fila.wbs and "." in fila.wbs:
        padre_wbs = fila.wbs.rsplit(".", 1)[0]
        if padre_wbs in por_wbs:
            return por_wbs[padre_wbs]
        avisos.append(
            f"«{fila.titulo}» referencia el WBS padre {padre_wbs}, que no existe: "
            "quedó en el primer nivel"
        )
        return None
    return ultimo_por_nivel.get(fila.nivel - 1)


def _vincular(
    session: Session,
    project_id: int,
    filas: list[FilaImportada],
    por_wbs: dict[str, int],
) -> list[str]:
    """Crea las dependencias. Cada una se valida contra el motor antes de guardarse."""
    avisos: list[str] = []
    for fila in filas:
        destino = por_wbs.get(fila.wbs)
        if destino is None:
            continue
        for crudo in fila.predecesoras:
            referencia = predecesoras_service.parsear(crudo)
            if referencia is None:
                avisos.append(
                    f"«{fila.titulo}»: no entiendo la predecesora «{crudo}», "
                    "se escribe 1.3 o 1.3+2"
                )
                continue
            codigo, lag, tipo = referencia
            origen = por_wbs.get(codigo)
            if origen is None:
                avisos.append(
                    f"«{fila.titulo}» depende del WBS {codigo}, que no está en la planilla: "
                    "la dependencia no se creó"
                )
                continue
            try:
                dependencies_service.crear(
                    session,
                    project_id,
                    DependenciaIn(
                        predecessor_id=origen,
                        successor_id=destino,
                        lag=lag,
                        tipo=tipo,
                    ),
                )
            except TareaInvalida as error:
                avisos.append(f"«{fila.titulo}» ← WBS {codigo}: {error}")
    return avisos
