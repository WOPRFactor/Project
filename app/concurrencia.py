"""Que dos personas trabajando a la vez no se pisen (Fase 12).

Tres piezas que resuelven el mismo problema desde ángulos distintos:

- **WAL.** En el modo por defecto (`journal_mode=DELETE`), un `INSERT` bloquea la base
  entera y cualquier lectura simultánea recibe «database is locked». En WAL los lectores
  no molestan al escritor ni el escritor a los lectores, que es exactamente la forma que
  tiene esta app: mucha lectura del tablero y escrituras cortas.
- **`busy_timeout`.** Sigue habiendo un solo escritor a la vez. Sin espera, el segundo
  falla al instante con un 500; con espera, se sienta unos segundos y en la práctica
  entra. Cinco segundos es mucho más de lo que tarda cualquier escritura de acá.
- **`Task.version`.** WAL y la espera evitan el error de base, no el problema real:
  dos personas editando la misma fila. La pantalla manda la versión que leyó y una
  versión vencida se **rechaza**; nunca se guarda encima en silencio.

La versión la sube un listener de `before_flush` y no cada service a mano: una tarea se
guarda desde el árbol, las predecesoras, los pesos y el import, y el que se olvidara de
subirla abriría justo el agujero que esto viene a tapar.
"""

from __future__ import annotations

from sqlalchemy import Engine, event
from sqlmodel import Session

from .models import Task

# Lo que espera un escritor a que se libere la base antes de darse por vencido.
ESPERA_OCUPADO_MS = 5000


def preparar_engine(motor: Engine) -> None:
    """Deja cada conexión nueva en WAL y con espera por lock.

    Va en el evento `connect` porque `busy_timeout` es por conexión. `journal_mode`
    en cambio queda escrito en el archivo, así que repetirlo es barato y de paso
    reacomoda una base que hubiera quedado en otro modo.
    """

    @event.listens_for(motor, "connect")
    def _al_conectar(conexion, _registro) -> None:  # pragma: no cover — lo corre SQLite
        cursor = conexion.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={ESPERA_OCUPADO_MS}")
        finally:
            cursor.close()


@event.listens_for(Session, "before_flush")
def _subir_version(session: Session, _contexto, _instancias) -> None:
    """Toda tarea que se guarde con cambios reales sube de versión.

    `is_modified` compara contra lo último confirmado, así que volver a guardar la
    fila sin tocar nada no la hace avanzar: si no, cualquier pantalla abierta en otra
    máquina quedaría en conflicto sin que nadie hubiera editado nada.
    """
    for objeto in session.dirty:
        if isinstance(objeto, Task) and session.is_modified(
            objeto, include_collections=False
        ):
            objeto.version = (objeto.version or 0) + 1


def esta_vencida(tarea: Task, version_leida: int | None) -> bool:
    """¿La pantalla que manda este guardado venía atrasada?

    `None` no bloquea a propósito: es una pantalla cargada antes de que existiera el
    campo, y negarle el guardado sería un error que el usuario no puede entender ni
    arreglar. Un número que no coincide sí: ahí hay una edición ajena de por medio.
    """
    if version_leida is None:
        return False
    return version_leida != tarea.version
