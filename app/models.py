"""Entidades persistidas. El árbol de tareas vive en `parent_id`."""

from __future__ import annotations

from datetime import date
from enum import Enum

from sqlmodel import Field, SQLModel


class EstadoProyecto(str, Enum):
    activo = "activo"
    pausado = "pausado"
    archivado = "archivado"


class Ambito(str, Enum):
    """En qué contador suma una tarea.

    Separa el alcance comprometido del acompañamiento posterior: una tarea de
    seguimiento que corre seis meses después del cierre no debería inflar la
    duración "del proyecto". **No afecta el cálculo**, solo el reporte — las
    dependencias y las fechas se computan igual para todas.
    """

    proyecto = "proyecto"
    seguimiento = "seguimiento"
    control = "control"


ETIQUETA_AMBITO = {
    Ambito.proyecto: "Proyecto",
    Ambito.seguimiento: "Seguimiento",
    Ambito.control: "Control",
}


class ColorEstado(str, Enum):
    """Paleta cerrada para los estados.

    Se guarda el *nombre* del color y no un hex: el valor termina en una clase CSS,
    así que un enum cerrado deja fuera de discusión que alguien escriba cualquier
    cosa ahí, y de paso los colores quedan consistentes entre proyectos.
    """

    gris = "gris"
    azul = "azul"
    verde = "verde"
    ambar = "ambar"
    rojo = "rojo"
    violeta = "violeta"


ETIQUETA_COLOR = {
    ColorEstado.gris: "Gris",
    ColorEstado.azul: "Azul",
    ColorEstado.verde: "Verde",
    ColorEstado.ambar: "Ámbar",
    ColorEstado.rojo: "Rojo",
    ColorEstado.violeta: "Violeta",
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


class Estado(SQLModel, table=True):
    """Un estado de tarea, definido por el usuario, por proyecto.

    Un estado con nombre libre no le sirve al motor: la app necesita saber si una
    tarea está terminada para contar el avance y para descartar hitos ya pasados.
    Por eso cada estado **declara su significado** con `es_final`, que es el único
    contrato entre el vocabulario del usuario y el cálculo. `avance_sugerido` es el
    puente hasta que exista avance real por tarea: es lo que la tarea aporta al
    avance ponderado mientras tanto.
    """

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    nombre: str = Field(max_length=40)
    color: ColorEstado = Field(default=ColorEstado.gris)
    orden: int = Field(default=0)
    # Terminal: la tarea no tiene más trabajo por delante. Reemplaza al viejo
    # `estado == "hecha"` clavado en el código.
    es_final: bool = Field(default=False)
    avance_sugerido: int = Field(default=0, ge=0, le=100)


# Los tres con los que arranca todo proyecto: mismo comportamiento que la v1, pero
# ahora son filas editables y no un enum del código.
ESTADOS_POR_DEFECTO = [
    ("Pendiente", ColorEstado.gris, False, 0),
    ("En curso", ColorEstado.azul, False, 50),
    ("Hecha", ColorEstado.verde, True, 100),
]


class Task(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    parent_id: int | None = Field(default=None, foreign_key="task.id", index=True)
    # Código tipo WBS (1, 1.2, 1.2.3). Es cómo el usuario referencia una tarea al
    # escribir dependencias, así que se genera al crear y después queda estable:
    # renumerar solo cuando lo pide, para no romper referencias escritas a mano.
    codigo: str = Field(default="", max_length=40, index=True)
    titulo: str = Field(max_length=200)
    notas: str = Field(default="", max_length=4000)
    responsable: str = Field(default="", max_length=120)
    # Criticidad de negocio: la decide el usuario por KPI o impacto. No confundir
    # con la ruta crítica, que el motor deduce del grafo y expone como holgura.
    critica: bool = Field(default=False)
    ambito: Ambito = Field(default=Ambito.proyecto)
    # Peso **como % del padre**, no del proyecto: así cada nivel cierra por su cuenta
    # y agregar una tarea no rompe la suma del árbol entero. `None` = repartir en
    # partes iguales lo que sobre. Ver `services/pesos.py`.
    peso: int | None = Field(default=None, ge=0, le=100)
    # duración 0 = hito: marca un momento, no consume días del cronograma
    duracion: int = Field(default=1, ge=0, le=3650)
    # Rango opcional: cuando la duración es una estimación y no un dato.
    duracion_optimista: int | None = Field(default=None, ge=0, le=3650)
    duracion_pesimista: int | None = Field(default=None, ge=0, le=3650)
    snet: date | None = Field(default=None)
    estado_id: int | None = Field(default=None, foreign_key="estado.id", index=True)
    orden: int = Field(default=0)


class TipoDependencia(str, Enum):
    """Ver `engine.types.TipoDependencia`: acá solo se persiste."""

    FS = "FS"
    SS = "SS"
    FF = "FF"


class Dependency(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    predecessor_id: int = Field(foreign_key="task.id", index=True)
    successor_id: int = Field(foreign_key="task.id", index=True)
    lag: int = Field(default=0, ge=-365, le=365)
    tipo: TipoDependencia = Field(default=TipoDependencia.FS)
