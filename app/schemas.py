"""Validación de todo lo que entra de afuera. Los routers no confían en nada más.

Los routers arman estos objetos desde el formulario; si algo no valida, Pydantic
levanta ValidationError y el manejador de errores lo convierte en un mensaje claro.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator

from .models import Ambito, ColorEstado, EstadoProyecto, TipoDependencia


def _texto_obligatorio(valor: str) -> str:
    """Recorta y exige contenido real: solo espacios no es un nombre."""
    limpio = valor.strip()
    if not limpio:
        raise ValueError("no puede quedar vacío")
    return limpio


class ProyectoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    descripcion: str = Field(default="", max_length=2000)
    fecha_inicio: date
    estado: EstadoProyecto = EstadoProyecto.activo

    @field_validator("nombre")
    @classmethod
    def nombre_con_contenido(cls, valor: str) -> str:
        return _texto_obligatorio(valor)

    @field_validator("descripcion")
    @classmethod
    def sin_espacios_sobrantes(cls, valor: str) -> str:
        return valor.strip()


class TareaIn(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    notas: str = Field(default="", max_length=4000)
    responsable: str = Field(default="", max_length=120)
    critica: bool = False
    ambito: Ambito = Ambito.proyecto
    # % del padre; None = lo que sobre, repartido en partes iguales.
    peso: int | None = Field(default=None, ge=0, le=100)
    duracion: int = Field(default=1, ge=0, le=3650)
    duracion_optimista: int | None = Field(default=None, ge=0, le=3650)
    duracion_pesimista: int | None = Field(default=None, ge=0, le=3650)
    snet: date | None = None
    # None = la tarea toma el estado inicial del proyecto. Los estados son filas, no
    # un enum, así que acá viaja un id y el service valida que sea de este proyecto.
    estado_id: int | None = None
    parent_id: int | None = None

    @field_validator("titulo")
    @classmethod
    def titulo_con_contenido(cls, valor: str) -> str:
        return _texto_obligatorio(valor)

    @field_validator("notas")
    @classmethod
    def sin_espacios_sobrantes(cls, valor: str) -> str:
        return valor.strip()


class EstadoIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=40)
    color: ColorEstado = ColorEstado.gris
    es_final: bool = False
    avance_sugerido: int = Field(default=0, ge=0, le=100)

    @field_validator("nombre")
    @classmethod
    def nombre_con_contenido(cls, valor: str) -> str:
        return _texto_obligatorio(valor)


class DependenciaIn(BaseModel):
    predecessor_id: int = Field(gt=0)
    successor_id: int = Field(gt=0)
    lag: int = Field(default=0, ge=-365, le=365)
    tipo: TipoDependencia = TipoDependencia.FS

    @field_validator("successor_id")
    @classmethod
    def distinta_de_si_misma(cls, valor: int, info) -> int:
        if info.data.get("predecessor_id") == valor:
            raise ValueError("Una tarea no puede depender de sí misma")
        return valor
