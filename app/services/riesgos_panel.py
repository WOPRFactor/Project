"""Arma la pantalla de riesgos: los dos cuadrantes, los conteos y los pendientes.

Vive aparte de `riesgos.py` —que es alta, baja y modificación— porque es otra
responsabilidad: leer el registro entero y dejarlo listo para pintar.

La decisión que manda acá son **los dos cuadrantes**. Uno solo obliga a elegir entre
dos lecturas que no son intercambiables: el inherente es el riesgo como está hoy y
justifica el plan; el residual es cómo queda si el plan se ejecuta, y es lo que se
promete hacia arriba. Mostrar solo el residual esconde de qué tamaño era el problema;
mostrar solo el inherente hace parecer que no se hizo nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session, select

from ..models import Contacto, EstadoRiesgo, Riesgo, Task
from . import matriz as matriz_service
from . import riesgos_alertas as alertas_service


@dataclass(frozen=True)
class Panel:
    """Todo lo que la pantalla de riesgos necesita, ya calculado."""

    riesgos: list[Riesgo]
    cuadrante: list[list[matriz_service.Celda]]
    por_zona: dict
    cuadrante_residual: list[list[matriz_service.Celda]]
    por_zona_residual: dict
    titulos: dict[int, str]
    personas: dict[int, str] = field(default_factory=dict)
    tareas: list[Task] = field(default_factory=list)
    alertas: list = field(default_factory=list)

    @property
    def abiertos(self) -> int:
        return len([r for r in self.riesgos if r.estado == EstadoRiesgo.abierto])

    @property
    def graves(self) -> list:
        return [a for a in self.alertas if a.grave]

    @property
    def exposicion(self) -> int:
        """Suma de severidades residuales de los que siguen vivos.

        Es un número sin unidad y no sirve para comparar proyectos; sirve para
        comparar el mismo proyecto contra sí mismo dos semanas después.
        """
        return sum(
            r.severidad_residual for r in self.riesgos if r.estado != EstadoRiesgo.cerrado
        )


def armar(session: Session, project_id: int, hoy: date | None = None) -> Panel:
    from . import riesgos as riesgos_service  # tardío: riesgos.py importa este módulo

    riesgos = riesgos_service.listar(session, project_id)
    # Un riesgo cerrado ya no ocupa lugar en el cuadrante: ensuciaría la lectura.
    vivos = [r for r in riesgos if r.estado != EstadoRiesgo.cerrado]
    inherente = [(r.id or 0, r.probabilidad, r.impacto) for r in vivos]
    residual = [(r.id or 0, r.probabilidad_hoy, r.impacto_hoy) for r in vivos]

    tareas = list(session.exec(select(Task).where(Task.project_id == project_id)))
    tareas.sort(key=lambda t: (t.codigo, t.id or 0))

    return Panel(
        riesgos=riesgos,
        cuadrante=matriz_service.cuadrante(inherente),
        por_zona=matriz_service.por_zona(inherente),
        cuadrante_residual=matriz_service.cuadrante(residual),
        por_zona_residual=matriz_service.por_zona(residual),
        titulos={t.id: t.titulo for t in tareas if t.id is not None},
        personas=_personas(session, project_id),
        tareas=tareas,
        alertas=alertas_service.revisar(riesgos, hoy),
    )


def _personas(session: Session, project_id: int) -> dict[int, str]:
    filas = session.exec(select(Contacto).where(Contacto.project_id == project_id))
    return {c.id: c.nombre for c in filas if c.id is not None}
