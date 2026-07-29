"""El registro de riesgos: entidades propias, aparte de `models.py`.

Se separa porque un riesgo bien llevado tiene tantos campos como una tarea —qué
puede pasar, cuánto pesa, qué se decidió hacer, cuánto queda después de hacerlo,
qué lo dispara, cuándo se revisa y quién responde— y todo eso adentro de `models.py`
lo empujaba contra el techo de tamaño sin que nada lo pidiera.

`models.py` lo reexporta, así el resto del código sigue importando de un solo lugar.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from sqlmodel import Field, SQLModel


class EstadoRiesgo(str, Enum):
    abierto = "abierto"
    mitigado = "mitigado"
    cerrado = "cerrado"
    materializado = "materializado"


ETIQUETA_ESTADO_RIESGO = {
    EstadoRiesgo.abierto: "Abierto",
    EstadoRiesgo.mitigado: "Mitigado",
    EstadoRiesgo.cerrado: "Cerrado",
    EstadoRiesgo.materializado: "Se materializó",
}


class Respuesta(str, Enum):
    """Qué se decidió hacer con el riesgo. Las cinco estrategias de siempre.

    `sin_definir` es el default a propósito: un riesgo anotado sin decisión tomada es
    lo normal al empezar, y poder contarlos es justamente lo que hace útil el registro.
    """

    sin_definir = "sin_definir"
    evitar = "evitar"
    mitigar = "mitigar"
    transferir = "transferir"
    aceptar = "aceptar"
    escalar = "escalar"


ETIQUETA_RESPUESTA = {
    Respuesta.sin_definir: "Sin definir",
    Respuesta.evitar: "Evitar",
    Respuesta.mitigar: "Mitigar",
    Respuesta.transferir: "Transferir",
    Respuesta.aceptar: "Aceptar",
    Respuesta.escalar: "Escalar",
}

# Las que se ejecutan haciendo algo, y por lo tanto deberían bajar el riesgo y tener
# un plan escrito. Aceptar y escalar no: aceptar es no hacer nada a propósito, y
# escalar es sacarlo de este proyecto.
RESPUESTAS_ACTIVAS = frozenset({Respuesta.evitar, Respuesta.mitigar, Respuesta.transferir})


class Riesgo(SQLModel, table=True):
    """Un riesgo del proyecto, colgado o no de una tarea.

    `task_id` es nullable a propósito: los riesgos más caros de un proyecto no cuelgan
    de ninguna tarea ("el cliente no libera el ambiente"), y una tarea puede tener
    más de uno. El tilde de la grilla es un atajo sobre esta tabla, no su reemplazo:
    un booleano no alcanzaría para ubicar nada en el cuadrante.

    Probabilidad e impacto son los **inherentes**: el riesgo como está hoy, sin contar
    el plan. El residual es el mismo par *después* de ejecutar la respuesta, y es lo
    que se reporta hacia arriba —"con lo que vamos a hacer, esto queda así"—. Se
    guarda aparte y no se deriva: cuánto baja un plan lo estima una persona.
    """

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    task_id: int | None = Field(default=None, foreign_key="task.id", index=True)
    descripcion: str = Field(default="", max_length=500)
    probabilidad: int = Field(default=3, ge=1, le=5)
    impacto: int = Field(default=3, ge=1, le=5)
    mitigacion: str = Field(default="", max_length=1000)
    responsable_id: int | None = Field(default=None, foreign_key="contacto.id", index=True)
    estado: EstadoRiesgo = Field(default=EstadoRiesgo.abierto)
    respuesta: Respuesta = Field(default=Respuesta.sin_definir)
    # `None` = todavía no se estimó, que no es lo mismo que "no baja". La lectura
    # cae al inherente y el registro lo avisa.
    probabilidad_residual: int | None = Field(default=None, ge=1, le=5)
    impacto_residual: int | None = Field(default=None, ge=1, le=5)
    # La señal observable de que el riesgo se está por convertir en problema. Sin
    # esto, un riesgo se "revisa" preguntando en una reunión.
    disparador: str = Field(default="", max_length=300)
    revisar_el: date | None = Field(default=None)
    # La tarea del cronograma que ejecuta la respuesta. Es distinta de `task_id`
    # —esa es la tarea *amenazada*—: un plan que no está en el cronograma no tiene
    # ni fecha ni responsable ni lugar donde verse.
    mitigacion_task_id: int | None = Field(default=None, foreign_key="task.id", index=True)

    @property
    def severidad(self) -> int:
        return self.probabilidad * self.impacto

    @property
    def probabilidad_hoy(self) -> int:
        """Residual si está estimado; si no, el inherente. Nunca inventa una baja."""
        return self.probabilidad_residual or self.probabilidad

    @property
    def impacto_hoy(self) -> int:
        return self.impacto_residual or self.impacto

    @property
    def severidad_residual(self) -> int:
        return self.probabilidad_hoy * self.impacto_hoy

    @property
    def residual_declarado(self) -> bool:
        return self.probabilidad_residual is not None or self.impacto_residual is not None
