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
    # Etapas plegadas (ids de tarea). Es orden visual, no filtro: los totales de
    # arriba y el cálculo siguen siendo del proyecto entero.
    colapsadas: frozenset[int] = frozenset()
    # Las flechas de dependencias del timeline: con muchas, son ruido — se apagan.
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

    @property
    def colapsadas_texto(self) -> str:
        return ",".join(str(i) for i in sorted(self.colapsadas))

    def esta_colapsada(self, tarea_id: int | None) -> bool:
        return tarea_id in self.colapsadas

    def alternar_colapso(self, tarea_id: int | None) -> str:
        """El valor de `colapsadas` que resulta de tocar el chevron de esta fila."""
        nuevas = self.colapsadas ^ {tarea_id or 0}
        return ",".join(str(i) for i in sorted(nuevas))

    def normalizada(self) -> "Mirada":
        """Lo que llega del formulario no se toma como viene."""
        return Mirada(
            detalle=self.detalle if self.detalle in DETALLES else TODO,
            etapa=self.etapa,
            color=self.color if self.color in MODOS_COLOR else POR_CRITICIDAD,
            columnas=frozenset(c for c in self.columnas if c in COLUMNAS),
            colapsadas=self.colapsadas,
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


def mirada_a_texto(mirada: Mirada) -> str:
    """La mirada entera en una línea, para guardarla como última vista del proyecto."""
    return (
        f"detalle={mirada.detalle}&etapa={mirada.etapa or 0}&color={mirada.color}"
        f"&columnas={mirada.columnas_texto}&colapsadas={mirada.colapsadas_texto}"
        f"&flechas={'1' if mirada.flechas else '0'}"
    )


def mirada_desde_texto(texto: str) -> Mirada:
    """La inversa. Un texto roto o viejo cae en los defaults: es una preferencia,
    no un dato — no amerita error."""
    partes = dict(p.split("=", 1) for p in texto.split("&") if "=" in p)
    etapa = partes.get("etapa", "0").strip()
    return Mirada(
        detalle=partes.get("detalle", TODO),
        etapa=int(etapa) if etapa.isdigit() and etapa != "0" else None,
        color=partes.get("color", POR_CRITICIDAD),
        columnas=(
            leer_columnas([partes["columnas"]] if partes["columnas"] else [])
            if "columnas" in partes
            else COLUMNAS_POR_DEFECTO
        ),
        colapsadas=leer_colapsadas(partes.get("colapsadas", "")),
        flechas=partes.get("flechas", "1") != "0",
    ).normalizada()


def leer_colapsadas(crudo: str) -> frozenset[int]:
    """Ids de las etapas plegadas, separados por coma. Lo que no sea número se tira."""
    return frozenset(
        int(p.strip()) for p in crudo.split(",") if p.strip().isdigit()
    )


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
    if mirada.colapsadas:
        visibles = _sin_colapsadas(visibles, mirada.colapsadas)
    return visibles


def _sin_colapsadas(filas: list["Fila"], colapsadas: frozenset[int]) -> list["Fila"]:
    """Las descendientes de una etapa plegada no se dibujan; la etapa sí, con su
    rollup y su barra, así el plegado no pierde las fechas del bloque."""
    hijas: dict[int | None, list[int]] = {}
    for fila in filas:
        hijas.setdefault(fila.tarea.parent_id, []).append(fila.tarea.id or 0)

    ocultas: set[int] = set()
    pila = [hija for raiz in colapsadas for hija in hijas.get(raiz, [])]
    while pila:
        actual = pila.pop()
        if actual in ocultas:
            continue
        ocultas.add(actual)
        pila.extend(hijas.get(actual, []))
    return [f for f in filas if (f.tarea.id or 0) not in ocultas]


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
