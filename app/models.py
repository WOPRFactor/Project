"""Entidades persistidas. El árbol de tareas vive en `parent_id`."""

from __future__ import annotations

from datetime import date
from enum import Enum

from sqlmodel import Field, SQLModel


class EstadoProyecto(str, Enum):
    activo = "activo"
    pausado = "pausado"
    archivado = "archivado"


class EstadoTarea(str, Enum):
    pendiente = "pendiente"
    en_curso = "en_curso"
    hecha = "hecha"


ETIQUETA_ESTADO_TAREA = {
    EstadoTarea.pendiente: "Pendiente",
    EstadoTarea.en_curso: "En curso",
    EstadoTarea.hecha: "Hecha",
}

ETIQUETA_ESTADO_PROYECTO = {
    EstadoProyecto.activo: "Activo",
    EstadoProyecto.pausado: "Pausado",
    EstadoProyecto.archivado: "Archivado",
}


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    nombre: str = Field(max_length=120, index=True)
    descripcion: str = Field(default="", max_length=2000)
    fecha_inicio: date
    estado: EstadoProyecto = Field(default=EstadoProyecto.activo)


class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    parent_id: int | None = Field(default=None, foreign_key="task.id", index=True)
    titulo: str = Field(max_length=200)
    notas: str = Field(default="", max_length=4000)
    duracion: int = Field(default=1, ge=1, le=3650)
    snet: date | None = Field(default=None)
    estado: EstadoTarea = Field(default=EstadoTarea.pendiente)
    orden: int = Field(default=0)


class Dependency(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    predecessor_id: int = Field(foreign_key="task.id", index=True)
    successor_id: int = Field(foreign_key="task.id", index=True)
    lag: int = Field(default=0, ge=-365, le=365)
