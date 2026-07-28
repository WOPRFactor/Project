"""Línea base: la foto del cronograma en el momento en que se aprobó.

Vive aparte de `models.py` porque es otra responsabilidad: `models` describe el
proyecto vivo, esto describe **fotos** de ese proyecto. Una foto no se edita nunca;
si el plan cambia, se congela otra.

Se guardan también `codigo` y `titulo` de cada tarea aunque estén en `Task`: una
tarea puede borrarse después de congelar, y el informe tiene que poder decir "esto
estaba comprometido y ya no está" en vez de mostrar un id huérfano.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Field, SQLModel


class LineaBase(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    nombre: str = Field(max_length=80)
    congelada_el: date
    # Puede haber varias (la aprobada, la replanificada); una sola es la vigente y es
    # contra la que se mide el desvío en la grilla y en el informe.
    vigente: bool = Field(default=True, index=True)
    nota: str = Field(default="", max_length=500)


class LineaBaseTarea(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    linea_base_id: int = Field(foreign_key="lineabase.id", index=True)
    task_id: int = Field(index=True)
    codigo: str = Field(default="", max_length=40)
    titulo: str = Field(default="", max_length=200)
    inicio: date | None = Field(default=None)
    fin: date | None = Field(default=None)
    duracion: int = Field(default=0)
    ambito: str = Field(default="proyecto", max_length=20)
    # El peso absoluto del momento: sin esto, el avance planificado de un informe
    # viejo se recalcularía con los pesos de hoy y dejaría de ser comparable.
    peso_absoluto: float = Field(default=0.0)
