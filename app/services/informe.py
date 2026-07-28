"""Arma el informe de estado a una fecha de corte. Devuelve **datos, no HTML**.

Un informe no es la grilla impresa: es la comparación entre lo que se prometió y lo
que está pasando. Por eso todo lo que sale de acá se apoya en la línea base, y por
eso no se emite con los pesos abiertos — un avance calculado sobre una cuenta que no
cierra es un número inventado, y este documento se manda a alguien.

Los números salen del mismo lugar que los de la pantalla (`vista.armar`), a
propósito: un informe que no coincide con el tablero hace más daño que no tener
informe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session

from ..models import Project
from ..models_base import LineaBase
from . import gantt_vista
from . import linea_base as linea_base_service
from . import projects as projects_service
from . import riesgos as riesgos_service
from . import vista as vista_service
from .resumen import Resumen, esta_hecha


class InformeInvalido(Exception):
    """No se puede emitir; el mensaje se le muestra al usuario."""


@dataclass
class Informe:
    proyecto: Project
    corte: date
    linea_base: LineaBase | None = None
    resumen: Resumen = field(default_factory=Resumen)
    por_ambito: list = field(default_factory=list)
    avance_real: int = 0
    avance_planificado: int | None = None
    desvio_ambito: dict = field(default_factory=dict)
    proximo_hito: object | None = None
    atrasadas: list = field(default_factory=list)
    en_riesgo: list = field(default_factory=list)
    hitos: list = field(default_factory=list)
    nuevas: list = field(default_factory=list)
    borradas: list = field(default_factory=list)
    riesgos: object | None = None
    # El Gantt del informe va en vista de etapas: un árbol de 200 filas no entra en A4.
    filas: list = field(default_factory=list)
    grilla: object | None = None
    flechas: list = field(default_factory=list)
    columna_hoy: int | None = None
    ancho_dia: int = 22
    alto_pista: int = 44
    desvios: dict = field(default_factory=dict)

    @property
    def hay_base(self) -> bool:
        return self.linea_base is not None

    @property
    def brecha(self) -> int | None:
        """Puntos de diferencia entre lo real y lo planificado. Negativo = atrasado."""
        if self.avance_planificado is None:
            return None
        return self.avance_real - self.avance_planificado


def armar(session: Session, project_id: int, corte: date | None = None) -> Informe:
    proyecto = projects_service.obtener(session, project_id)
    if proyecto is None:
        raise InformeInvalido("Ese proyecto no existe")

    corte = corte or date.today()
    base = linea_base_service.fechas_base(session, project_id)
    datos = vista_service.armar(
        session, project_id, hoy=corte,
        mirada=gantt_vista.Mirada(detalle=gantt_vista.ETAPAS), base=base,
    )
    if datos.error:
        raise InformeInvalido(f"El cronograma no se puede calcular: {datos.error}")
    if not datos.todas_las_filas:
        raise InformeInvalido("El proyecto no tiene tareas")
    if datos.niveles_abiertos:
        detalle = "; ".join(n.mensaje for n in datos.niveles_abiertos)
        raise InformeInvalido(
            "Los pesos no cierran, así que el avance de este informe no significaría "
            f"nada. Cerralos antes de emitirlo — {detalle}"
        )

    desvios = linea_base_service.desvios(session, project_id, datos)
    hojas = [f for f in datos.todas_las_filas if not f.es_resumen]

    return Informe(
        proyecto=proyecto,
        corte=corte,
        linea_base=linea_base_service.vigente(session, project_id),
        resumen=datos.resumen,
        por_ambito=datos.por_ambito,
        avance_real=datos.avance_ponderado,
        avance_planificado=linea_base_service.avance_planificado(session, project_id, corte),
        desvio_ambito=linea_base_service.desvio_por_ambito(session, project_id, datos),
        proximo_hito=datos.proximo_hito,
        atrasadas=_atrasadas(hojas),
        en_riesgo=_en_riesgo(hojas),
        hitos=[f for f in datos.todas_las_filas if f.es_hito],
        nuevas=[f for f in hojas if f.es_nueva],
        borradas=[d for d in desvios.values() if d.fue_borrada],
        riesgos=riesgos_service.panel(session, project_id),
        filas=datos.filas,
        grilla=datos.grilla,
        flechas=datos.flechas,
        columna_hoy=datos.columna_hoy,
        ancho_dia=datos.ancho_dia,
        alto_pista=datos.alto_pista,
        desvios=desvios,
    )


def _atrasadas(hojas: list) -> list:
    """Las que terminan más tarde que lo prometido, la peor primero."""
    return sorted(
        [f for f in hojas if f.desvio is not None and f.desvio > 0],
        key=lambda f: -f.desvio,
    )


def _en_riesgo(hojas: list) -> list:
    """Sin holgura y sin terminar: cualquier demora acá mueve el fin de su ámbito.

    Es distinto de «atrasada»: acá todavía no pasó nada, pero no hay colchón. Es la
    lista que sirve para actuar, no para explicar.
    """
    return [f for f in hojas if f.sin_holgura and not esta_hecha(f) and f.tarea.avance < 100]
