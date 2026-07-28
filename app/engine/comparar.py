"""Comparación entre el cronograma congelado y el de hoy. Python puro, sin DB.

El desvío es lo único que convierte un informe en información: sin un término de
comparación, "termina el 25/10" no dice si vamos bien o mal. Acá se calcula contra
la **línea base**, que es la foto del cronograma en el momento en que alguien lo
aprobó.

Convención de signo, elegida para que se lea sin pensar: **positivo = atrasado**.
Un desvío de +12 son doce días hábiles más tarde que lo prometido.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .calendar import contar_habiles


@dataclass(frozen=True)
class Congelada:
    """Una tarea tal como quedó en la foto, o tal como está hoy."""

    task_id: int
    titulo: str
    inicio: date | None = None
    fin: date | None = None
    duracion: int = 0
    ambito: str = "proyecto"


@dataclass(frozen=True)
class Desvio:
    """Cuánto se movió una tarea respecto de la base."""

    task_id: int
    titulo: str
    dias: int = 0
    base_inicio: date | None = None
    base_fin: date | None = None
    fin: date | None = None
    # Una tarea que no estaba en la base no tiene desvío: tiene *alcance nuevo*, que
    # es otra conversación y por eso se reporta aparte en vez de contarse como atraso.
    es_nueva: bool = False
    fue_borrada: bool = False

    @property
    def atrasada(self) -> bool:
        return self.dias > 0

    @property
    def adelantada(self) -> bool:
        return self.dias < 0

    @property
    def comparable(self) -> bool:
        return not self.es_nueva and not self.fue_borrada


def dias_habiles_con_signo(desde: date, hasta: date) -> int:
    """Días hábiles entre dos fechas, negativo si `hasta` cae antes."""
    if hasta >= desde:
        return contar_habiles(desde, hasta) - 1
    return -(contar_habiles(hasta, desde) - 1)


def comparar(base: list[Congelada], actual: list[Congelada]) -> list[Desvio]:
    """Un `Desvio` por tarea, en el orden del cronograma actual y con las borradas al final."""
    por_id_base = {c.task_id: c for c in base}
    salida: list[Desvio] = []

    for tarea in actual:
        congelada = por_id_base.get(tarea.task_id)
        if congelada is None:
            salida.append(Desvio(
                tarea.task_id, tarea.titulo, fin=tarea.fin, es_nueva=True
            ))
            continue
        salida.append(Desvio(
            task_id=tarea.task_id,
            titulo=tarea.titulo,
            dias=_movimiento(congelada.fin, tarea.fin),
            base_inicio=congelada.inicio,
            base_fin=congelada.fin,
            fin=tarea.fin,
        ))

    vivas = {t.task_id for t in actual}
    for congelada in base:
        if congelada.task_id not in vivas:
            salida.append(Desvio(
                congelada.task_id, congelada.titulo,
                base_inicio=congelada.inicio, base_fin=congelada.fin,
                fue_borrada=True,
            ))
    return salida


def _movimiento(base_fin: date | None, fin: date | None) -> int:
    if base_fin is None or fin is None:
        return 0
    return dias_habiles_con_signo(base_fin, fin)


def por_ambito(base: list[Congelada], actual: list[Congelada]) -> dict[str, int]:
    """Cuánto se corrió el fin de cada ámbito. Es el titular del informe.

    Se mira el **fin del bloque**, no la suma de los desvíos de sus tareas: cinco
    tareas atrasadas cinco días cada una que corren en paralelo mueven el bloque
    cinco días, no veinticinco.
    """
    salida: dict[str, int] = {}
    for ambito in {c.ambito for c in base} | {c.ambito for c in actual}:
        fin_base = _ultimo(base, ambito)
        fin_actual = _ultimo(actual, ambito)
        if fin_base is None or fin_actual is None:
            continue
        salida[ambito] = dias_habiles_con_signo(fin_base, fin_actual)
    return salida


def _ultimo(tareas: list[Congelada], ambito: str) -> date | None:
    fines = [t.fin for t in tareas if t.ambito == ambito and t.fin]
    return max(fines) if fines else None
