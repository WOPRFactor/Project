"""Identidad: cuentas y sesiones (Fase 10).

Vive aparte de `models.py` por responsabilidad: acá no hay nada del dominio de
proyectos, y así se lee de un saque qué tablas son la puerta de entrada.

Dos decisiones que se explican solas al leerlas:

- **La sesión es una fila, no una cookie firmada.** Una cookie firmada no se puede
  revocar antes de que expire: si echás a alguien o se filtra un token, seguís
  esperando. Con tabla, "revocar ya" es un DELETE.
- **No hay auto-registro.** Las cuentas las crea el admin y entrega una contraseña
  de un solo uso que se cambia al primer ingreso (`debe_cambiar_password`). Eso
  elimina el registro público, la verificación por mail y el abuso de altas.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class Usuario(SQLModel, table=True):
    """Una cuenta. El hash nunca sale de acá: ni a un log ni a una respuesta."""

    id: int | None = Field(default=None, primary_key=True)
    # El mail es el nombre de usuario. Se guarda normalizado (minúsculas, sin
    # espacios) para que «Ariel@x.com» y «ariel@x.com» sean la misma cuenta.
    mail: str = Field(max_length=160, index=True, unique=True)
    nombre: str = Field(default="", max_length=120)
    hash_password: str = Field(max_length=200)
    activo: bool = Field(default=True)
    es_admin: bool = Field(default=False)
    # Contraseña de un solo uso: el primer login obliga a cambiarla.
    debe_cambiar_password: bool = Field(default=True)
    creado_el: datetime = Field(default_factory=datetime.now)
    ultimo_ingreso: datetime | None = Field(default=None)


class Rol(str, Enum):
    """Qué puede hacer alguien **en un proyecto**. Tres, y no más (Fase 11).

    Permisos por tarea o por columna quedan explícitamente afuera del plan: la
    complejidad no se paga sola y vuelve imposible razonar sobre quién ve qué.
    """

    duenio = "dueño"
    editor = "editor"
    lector = "lector"


ETIQUETA_ROL = {
    Rol.duenio: "Dueño",
    Rol.editor: "Editor",
    Rol.lector: "Lector",
}

DESCRIPCION_ROL = {
    Rol.duenio: "Administra miembros, pesos y línea base. Puede borrar el proyecto.",
    Rol.editor: "Carga y edita el cronograma. No toca miembros ni línea base.",
    Rol.lector: "Solo mira. No puede modificar nada.",
}


class Miembro(SQLModel, table=True):
    """Quién participa de un proyecto y con qué rol.

    El **dueño es un permiso**; el responsable (`Project.responsable_id`, un
    `Contacto`) es una rendición de cuentas. No son lo mismo y no tienen por qué
    ser la misma persona: el dueño administra, el responsable rinde.
    """

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    rol: Rol = Field(default=Rol.editor)
    creado_el: datetime = Field(default_factory=datetime.now)


class Sesion(SQLModel, table=True):
    """Una sesión abierta. El token es opaco y solo vive en la cookie del navegador.

    `expira_el` es la antigüedad máxima y `visto_el` la última actividad: se cierra
    por las dos vías, así una pestaña olvidada no queda válida para siempre.
    """

    id: int | None = Field(default=None, primary_key=True)
    token: str = Field(max_length=64, index=True, unique=True)
    usuario_id: int = Field(foreign_key="usuario.id", index=True)
    creada_el: datetime = Field(default_factory=datetime.now)
    visto_el: datetime = Field(default_factory=datetime.now)
    expira_el: datetime
    # Se guarda para el listado de sesiones ("cerrar las demás"), no para autenticar.
    agente: str = Field(default="", max_length=200)
