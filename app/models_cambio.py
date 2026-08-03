"""Auditoría: qué cambió, quién lo cambió y cuándo (Fase 12).

Vive aparte de `models.py` por la misma razón que la línea base: `models` describe el
proyecto **como está hoy**, esto describe **lo que le pasó**. Son dos vidas distintas.

Tres decisiones que no son obvias:

- **Es de solo agregar.** No hay ruta que edite ni borre un `Cambio`, y no la va a
  haber: una auditoría que se puede corregir no sirve para lo único que sirve una
  auditoría.
- **Los valores se guardan como texto ya legible** («Hecha», «Ariel Clerici»), no como
  ids. Un id de estado borrado dentro de tres meses no se puede volver a resolver, y el
  historial dejaría de reconstruir nada.
- **`task_id` no declara FK y `etiqueta` copia el código y el título.** La tarea se
  puede borrar; su historia no. Sin la copia, el registro del borrado sería un número
  huérfano justo en el caso en que más importa.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel


class Cambio(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    # Sin FK a propósito: la tarea puede dejar de existir y la fila tiene que quedar.
    task_id: int | None = Field(default=None, index=True)
    # Quién. Nullable porque hay escrituras sin usuario detrás: el import de una
    # planilla desde un script, o las migraciones de datos del arranque.
    usuario_id: int | None = Field(default=None, foreign_key="usuario.id", index=True)
    cuando: datetime = Field(default_factory=datetime.now, index=True)
    # Código y título de la tarea en el momento del cambio.
    etiqueta: str = Field(default="", max_length=250)
    # Qué campo se tocó, con el nombre que ve el usuario en la grilla («Días», «Peso»).
    campo: str = Field(default="", max_length=40)
    antes: str = Field(default="", max_length=250)
    despues: str = Field(default="", max_length=250)
