"""Calendario de días hábiles (lunes a viernes, sin feriados en v1).

Toda la aritmética de fechas del motor pasa por acá. Si en v2 entran feriados,
este es el único archivo que cambia.
"""

from __future__ import annotations

from datetime import date, timedelta

_SABADO = 5


def es_habil(dia: date) -> bool:
    return dia.weekday() < _SABADO


def siguiente_habil(dia: date) -> date:
    """El mismo día si es hábil; si no, el próximo lunes."""
    while not es_habil(dia):
        dia += timedelta(days=1)
    return dia


def anterior_habil(dia: date) -> date:
    """El mismo día si es hábil; si no, el viernes previo."""
    while not es_habil(dia):
        dia -= timedelta(days=1)
    return dia


def sumar_habiles(dia: date, n: int) -> date:
    """Mueve `n` días hábiles desde `dia` (negativo = hacia atrás).

    El punto de partida se ajusta al día hábil correspondiente al sentido del
    movimiento, así sumar 0 sobre un sábado devuelve un día hábil real.
    """
    actual = siguiente_habil(dia) if n >= 0 else anterior_habil(dia)
    paso = timedelta(days=1 if n >= 0 else -1)
    restantes = abs(n)
    while restantes:
        actual += paso
        if es_habil(actual):
            restantes -= 1
    return actual


def fin_desde_inicio(inicio: date, duracion: int) -> date:
    """Último día hábil de una tarea que arranca en `inicio` y dura `duracion` días."""
    if duracion < 1:
        raise ValueError("La duración debe ser de al menos 1 día hábil")
    return sumar_habiles(inicio, duracion - 1)


def contar_habiles(desde: date, hasta: date) -> int:
    """Cantidad de días hábiles en el rango inclusivo [desde, hasta]. 0 si está invertido."""
    if hasta < desde:
        return 0
    total = 0
    actual = siguiente_habil(desde)
    while actual <= hasta:
        total += 1
        actual = sumar_habiles(actual, 1)
    return total
