"""Contratos del import y aplicación de lo importado a la base.

Un import es un dato en dos partes: las filas que se van a crear y los **avisos**
sobre lo que hubo que arreglar o saltear. Nada se repara en silencio.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date

from sqlmodel import Session

from ..models import Project
from ..schemas import DependenciaIn, ProyectoIn, TareaIn
from . import dependencies as dependencies_service
from . import projects as projects_service
from . import tasks as tasks_service
from .tasks import TareaInvalida

TIPOS = {"fase", "tarea", "hito"}


@dataclass
class FilaImportada:
    """Una fila lista para convertirse en tarea."""

    titulo: str
    wbs: str = ""
    tipo: str = "tarea"
    duracion: int = 1
    responsable: str = ""
    predecesoras: list[str] = field(default_factory=list)
    nivel: int = 0

    @property
    def es_hito(self) -> bool:
        return self.tipo == "hito"


@dataclass
class Importacion:
    """Resultado de leer una fuente: qué se importaría y qué hay que mirar."""

    filas: list[FilaImportada] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    origen: str = ""

    @property
    def resumen(self) -> str:
        cuenta: dict[str, int] = {}
        for fila in self.filas:
            cuenta[fila.tipo] = cuenta.get(fila.tipo, 0) + 1
        partes = [f"{cuenta[t]} {t}{'s' if cuenta[t] > 1 else ''}" for t in sorted(cuenta)]
        vinculos = sum(len(f.predecesoras) for f in self.filas)
        return f"{len(self.filas)} filas ({', '.join(partes)}) y {vinculos} dependencias"


MAX_FILAS = 2000
MAX_PREDECESORAS = 50


def a_json(importacion: Importacion) -> str:
    """Serializa la previsualización para que viaje en un campo oculto del formulario."""
    return json.dumps([asdict(f) for f in importacion.filas], ensure_ascii=False)


def desde_json(carga: str) -> Importacion | None:
    """Reconstruye la previsualización que vuelve del navegador.

    Viene del cliente, así que se trata como input externo: tipos estrictos,
    longitudes acotadas y descarte de todo lo que no encaje. Después, cada tarea
    y cada dependencia pasa igual por la validación de siempre.
    """
    try:
        crudas = json.loads(carga)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(crudas, list) or len(crudas) > MAX_FILAS:
        return None

    importacion = Importacion(origen="previsualización confirmada")
    for cruda in crudas:
        if not isinstance(cruda, dict):
            continue
        titulo = str(cruda.get("titulo", "")).strip()[:200]
        if not titulo:
            continue
        tipo = cruda.get("tipo")
        predecesoras = cruda.get("predecesoras")
        importacion.filas.append(
            FilaImportada(
                titulo=titulo,
                wbs=str(cruda.get("wbs", ""))[:40],
                tipo=tipo if tipo in TIPOS else "tarea",
                duracion=_entero(cruda.get("duracion"), 1, 0, 3650),
                responsable=str(cruda.get("responsable", ""))[:120],
                predecesoras=[
                    str(p)[:40]
                    for p in (predecesoras if isinstance(predecesoras, list) else [])
                ][:MAX_PREDECESORAS],
                nivel=_entero(cruda.get("nivel"), 0, 0, 20),
            )
        )
    return importacion


def _entero(valor, default: int, minimo: int, maximo: int) -> int:
    try:
        return max(minimo, min(int(valor), maximo))
    except (TypeError, ValueError):
        return default


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
                duracion=0 if fila.es_hito else max(fila.duracion, 1),
                parent_id=padre_id,
            ),
        )
        if fila.wbs:
            por_wbs[fila.wbs] = tarea.id
        ultimo_por_nivel[fila.nivel] = tarea.id
        for mas_hondo in [n for n in ultimo_por_nivel if n > fila.nivel]:
            del ultimo_por_nivel[mas_hondo]

    avisos += _vincular(session, proyecto.id, importacion.filas, por_wbs)
    return proyecto, avisos


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
        for codigo in fila.predecesoras:
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
                    DependenciaIn(predecessor_id=origen, successor_id=destino),
                )
            except TareaInvalida as error:
                avisos.append(f"«{fila.titulo}» ← WBS {codigo}: {error}")
    return avisos
