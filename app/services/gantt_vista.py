"""Qué filas se dibujan del Gantt y de qué color. Módulo puro: sin base ni sesión.

Dos decisiones de presentación, un solo archivo, porque son la misma pregunta desde
dos lados: *qué se ve*.

Dos reglas que no son cosméticas:

1. **El filtro no cambia los totales.** El cronograma se calcula siempre entero —si no,
   las dependencias con las tareas ocultas darían fechas distintas— y el resumen de
   arriba sigue siendo el del proyecto completo. Un Gantt filtrado que además cambiara
   los números de arriba es una captura de pantalla lista para engañar a alguien.
2. **El color nunca es la única señal.** Los modos son excluyentes (dos criterios de
   color a la vez dan barro) y la barra siempre lleva además el título y el tooltip,
   así el Gantt sigue leyéndose impreso en blanco y negro.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover — solo el tipo, sin import circular
    from .vista import Fila

TODO = "todo"
ETAPAS = "etapas"

DETALLES = {
    TODO: "Todo el árbol",
    ETAPAS: "Solo etapas e hitos",
    "n1": "Hasta el nivel 2",
    "n2": "Hasta el nivel 3",
}

POR_CRITICIDAD = "criticidad"
POR_ESTADO = "estado"
POR_AMBITO = "ambito"
POR_AVANCE = "avance"

MODOS_COLOR = {
    POR_CRITICIDAD: "Criticidad",
    POR_ESTADO: "Estado",
    POR_AMBITO: "Ámbito",
    POR_AVANCE: "Avance",
}

# Columnas opcionales de la grilla. WBS y Tarea no están acá porque no se pueden
# apagar: sin ellas la fila no se puede identificar ni referenciar.
COLUMNAS = {
    "resp": "Resp.",
    "pred": "Predec.",
    "dias": "Días",
    "rango": "Opt · Pes",
    "inicio": "Inicio",
    "fin": "Fin",
    "desvio": "Desvío",
    "crit": "Crít.",
    "peso": "Peso",
    "avance": "Avance",
    "riesgo": "Riesgo",
    "estado": "Estado",
    "ambito": "Ámbito",
}

# Lo que se ve sin tocar nada. Deliberadamente **no son todas**: la grilla queda
# anclada a la izquierda, así que cada columna prendida es ancho que el Gantt pierde.
# Este conjunto entra en el tope del panel sin scroll interno; Desvío, Estado, Peso,
# Riesgo, Ámbito y Opt·Pes están a un clic en el selector.
COLUMNAS_POR_DEFECTO = frozenset({
    "resp", "pred", "dias", "inicio", "fin", "avance",
})


@dataclass(frozen=True)
class Mirada:
    """Cómo está mirando el usuario la grilla ahora mismo."""

    detalle: str = TODO
    etapa: int | None = None
    color: str = POR_CRITICIDAD
    columnas: frozenset[str] = COLUMNAS_POR_DEFECTO
    # Las flechas entre predecesoras son informativas pero con muchas
    # dependencias tapan las barras; se apagan sin perder el dato.
    flechas: bool = True

    @property
    def filtrada(self) -> bool:
        return self.detalle != TODO or self.etapa is not None

    def ve(self, columna: str) -> bool:
        return columna in self.columnas

    @property
    def columnas_texto(self) -> str:
        """Para que la mirada viaje en un `hx-vals` y vuelva igual."""
        return ",".join(sorted(self.columnas))

    def normalizada(self) -> "Mirada":
        """Lo que llega del formulario no se toma como viene."""
        return Mirada(
            detalle=self.detalle if self.detalle in DETALLES else TODO,
            etapa=self.etapa,
            color=self.color if self.color in MODOS_COLOR else POR_CRITICIDAD,
            columnas=frozenset(c for c in self.columnas if c in COLUMNAS),
            flechas=self.flechas,
        )


def leer_columnas(crudo: list[str] | None) -> frozenset[str]:
    """Acepta las dos formas en que llegan: repetidas (checkboxes) o separadas por
    coma (el `hx-vals` que viaja en cada mutación). Ausente = las de por defecto;
    presente y vacío = solo WBS y Tarea, que es una elección válida."""
    if crudo is None:
        return COLUMNAS_POR_DEFECTO
    partes = [p.strip() for valor in crudo for p in valor.split(",") if p.strip()]
    return frozenset(p for p in partes if p in COLUMNAS)


def filtrar(filas: list["Fila"], mirada: Mirada) -> list["Fila"]:
    """Las filas que se dibujan. El cálculo ya se hizo sobre todas."""
    visibles = filas
    if mirada.etapa is not None:
        visibles = _rama(visibles, mirada.etapa)
    if mirada.detalle == ETAPAS:
        # Nivel 0 más los hitos de cualquier profundidad: los hitos son justamente
        # lo que se reporta, esconderlos dejaría la vista de una página sin marcas.
        visibles = [f for f in visibles if f.nivel == 0 or f.es_hito]
    elif mirada.detalle in ("n1", "n2"):
        tope = int(mirada.detalle[1])
        visibles = [f for f in visibles if f.nivel <= tope or f.es_hito]
    return visibles


def _rama(filas: list["Fila"], raiz_id: int) -> list["Fila"]:
    """La etapa elegida y todo lo que cuelga de ella."""
    hijas: dict[int | None, list[int]] = {}
    for fila in filas:
        hijas.setdefault(fila.tarea.parent_id, []).append(fila.tarea.id or 0)

    dentro = {raiz_id}
    pila = list(hijas.get(raiz_id, []))
    while pila:
        actual = pila.pop()
        if actual in dentro:
            continue
        dentro.add(actual)
        pila.extend(hijas.get(actual, []))
    return [f for f in filas if (f.tarea.id or 0) in dentro]


def etapas(filas: list["Fila"]) -> list["Fila"]:
    """Las candidatas del selector de etapa: lo que cuelga de la raíz."""
    return [f for f in filas if f.nivel == 0]


# La columna Tarea se dimensiona sola: es la única cuyo contenido no tiene un largo
# acotado, y es la que más importa leer entera. Se estima por cantidad de caracteres
# —la fuente es proporcional, así que es una aproximación— pero queda encerrada entre
# un mínimo y un máximo, así que equivocarse por poco no rompe nada.
_ANCHO_CARACTER = 7.2
_SANGRIA_POR_NIVEL = 14
_TAREA_MINIMO = 260
# Tope deliberadamente moderado: el auto-ajuste busca que la mayoría de los
# títulos entren, no que entre el más largo. Pasado esto la columna sola se
# comería el panel y dejaría el resto fuera de vista; para esos casos están el
# tooltip y el arrastre del borde.
_TAREA_MAXIMO = 620


def ancho_tarea(filas: list["Fila"]) -> int:
    """Ancho en píxeles para la columna Tarea, según el título más largo que se ve."""
    if not filas:
        return _TAREA_MINIMO
    mas_ancho = max(
        len(f.tarea.titulo) * _ANCHO_CARACTER + f.nivel * _SANGRIA_POR_NIVEL
        for f in filas
    )
    return int(max(_TAREA_MINIMO, min(_TAREA_MAXIMO, mas_ancho + 34)))


def avance(fila: "Fila") -> int:
    """Cuánto de la barra va pintado: el avance real que cargó el usuario."""
    return max(0, min(100, fila.tarea.avance))


def clase_color(fila: "Fila", modo: str) -> str:
    """Un tono por fila según el criterio elegido. Los resúmenes no se pintan.

    Una barra de resumen es una envolvente, no trabajo: darle color de estado o de
    avance sugeriría un dato que no tiene.
    """
    if fila.es_resumen:
        return "resumen"
    if modo == POR_ESTADO:
        return f"color-{fila.estado.color.value}" if fila.estado else "color-gris"
    if modo == POR_AMBITO:
        return f"ambito-barra-{fila.tarea.ambito.value}"
    if modo == POR_AVANCE:
        return _por_avance(avance(fila))
    return "critica" if fila.tarea.critica else "color-azul"


def _por_avance(porcentaje: int) -> str:
    if porcentaje >= 100:
        return "color-verde"
    if porcentaje >= 50:
        return "color-azul"
    if porcentaje > 0:
        return "color-ambar"
    return "color-gris"
