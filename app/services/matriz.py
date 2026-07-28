"""Matriz de riesgo 5×5. Módulo puro: sin base, sin sesión, sin HTML.

Severidad = probabilidad × impacto, y cuatro zonas sobre ese producto. La escala 5×5
es la estándar (la que espera cualquiera que haya visto una matriz de riesgo); una
3×3 se llena más rápido pero apelmaza todo en el medio y deja de discriminar.

Se dibuja después con CSS Grid, igual que el Gantt: no entra una librería de
gráficos para pintar veinticinco celdas.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

ESCALA = 5


class Zona(str, Enum):
    bajo = "bajo"
    medio = "medio"
    alto = "alto"
    critico = "critico"


ETIQUETA_ZONA = {
    Zona.bajo: "Bajo",
    Zona.medio: "Medio",
    Zona.alto: "Alto",
    Zona.critico: "Crítico",
}

ETIQUETA_PROBABILIDAD = {
    1: "Muy baja", 2: "Baja", 3: "Media", 4: "Alta", 5: "Muy alta",
}

ETIQUETA_IMPACTO = {
    1: "Insignificante", 2: "Menor", 3: "Moderado", 4: "Mayor", 5: "Crítico",
}


@dataclass(frozen=True)
class Celda:
    """Una casilla del cuadrante con los riesgos que caen adentro."""

    probabilidad: int
    impacto: int
    riesgos: tuple[int, ...] = ()

    @property
    def severidad(self) -> int:
        return self.probabilidad * self.impacto

    @property
    def zona(self) -> Zona:
        return zona(self.severidad)

    @property
    def cuantos(self) -> int:
        return len(self.riesgos)


def acotar(valor: int) -> int:
    """La escala es 1..5 y nada más: un valor fuera de rango se recorta, no explota."""
    return max(1, min(ESCALA, valor))


def severidad(probabilidad: int, impacto: int) -> int:
    return acotar(probabilidad) * acotar(impacto)


def zona(severidad_: int) -> Zona:
    if severidad_ <= 4:
        return Zona.bajo
    if severidad_ <= 9:
        return Zona.medio
    if severidad_ <= 14:
        return Zona.alto
    return Zona.critico


def cuadrante(riesgos: list[tuple[int, int, int]]) -> list[list[Celda]]:
    """El 5×5 listo para pintar: `(id, probabilidad, impacto)` por riesgo.

    Devuelve las filas **de mayor a menor probabilidad**, que es como se lee una
    matriz de riesgo: lo peor arriba a la derecha.
    """
    ubicados: dict[tuple[int, int], list[int]] = {}
    for identificador, probabilidad, impacto in riesgos:
        clave = (acotar(probabilidad), acotar(impacto))
        ubicados.setdefault(clave, []).append(identificador)

    return [
        [
            Celda(p, i, tuple(ubicados.get((p, i), ())))
            for i in range(1, ESCALA + 1)
        ]
        for p in range(ESCALA, 0, -1)
    ]


def por_zona(riesgos: list[tuple[int, int, int]]) -> dict[Zona, int]:
    """Cuántos riesgos hay en cada zona. Es el titular del informe."""
    conteo = {z: 0 for z in Zona}
    for _, probabilidad, impacto in riesgos:
        conteo[zona(severidad(probabilidad, impacto))] += 1
    return conteo
