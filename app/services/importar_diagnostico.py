"""Detecta cuándo las fechas de una planilla contradicen sus propias dependencias.

Una planilla hecha a mano suele decir una cosa en la columna Predec. y otra en las
columnas de fechas: dos tareas declaradas en serie que figuran arrancando el mismo
día. Importarla en silencio da un cronograma distinto al que el autor tenía en la
cabeza, y nadie entiende por qué.

**No se comparan fechas absolutas.** Si arrancás el proyecto en otra fecha, todo se
corre parejo y eso no dice nada. Lo que se compara es la *relación* entre cada tarea
y su predecesora dentro de los propios números de la planilla: ahí sí, si B figura
arrancando el mismo día que A pero está declarada Fin→Inicio, hay una contradicción
real y se puede nombrar el tipo que la explica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..engine.calendar import contar_habiles, sumar_habiles
from .importar import FilaImportada, Importacion
from .predecesoras import parsear


@dataclass
class Discrepancia:
    """Una dependencia cuya declaración no coincide con las fechas de la planilla.

    `estructural` separa dos cosas muy distintas. Si la planilla muestra que dos
    tareas arrancan juntas, la relación estaba mal declarada y corregirla es
    objetivamente mejor. Si en cambio muestra una tarea puesta meses después de lo
    que exigen sus dependencias, eso es una fecha escrita a mano: convertirla en un
    lag duro reproduce la planilla pero **congela el accidente** y deja el
    cronograma sordo a cambios reales. Eso se reporta, no se aplica.
    """

    wbs: str
    titulo: str
    predecesora: str
    sugerencia: str
    motivo: str
    estructural: bool = True

    def __str__(self) -> str:
        return f"{self.wbs} «{self.titulo[:44]}»: {self.motivo} → escribí «{self.sugerencia}»"


@dataclass
class Diagnostico:
    discrepancias: list[Discrepancia] = field(default_factory=list)
    revisadas: int = 0

    @property
    def hay_algo(self) -> bool:
        return bool(self.discrepancias)

    @property
    def estructurales(self) -> list[Discrepancia]:
        """Relaciones mal declaradas: se pueden corregir con confianza."""
        return [d for d in self.discrepancias if d.estructural]

    @property
    def a_revisar(self) -> list[Discrepancia]:
        """Fechas puestas a mano: las mira una persona, no se tocan solas."""
        return [d for d in self.discrepancias if not d.estructural]

    @property
    def resumen(self) -> str:
        partes = []
        if self.estructurales:
            partes.append(f"{len(self.estructurales)} relaciones mal declaradas")
        if self.a_revisar:
            partes.append(f"{len(self.a_revisar)} fechas puestas a mano")
        return "; ".join(partes) + f" (de {self.revisadas} dependencias)"


# Un hueco chico entre lo exigido y lo declarado es ruido de ajuste manual; recién
# a partir de una semana hábil vale la pena preguntarse si falta una dependencia.
_HUECO_MINIMO = 5

# Hasta acá un solape es una decisión de planificación (arrancar antes de que la
# anterior termine). Más que esto es una fecha escrita a mano, no una relación.
_SOLAPE_CREIBLE = 10


def analizar(importacion: Importacion, inicio_proyecto: date | None = None) -> Diagnostico:
    """Revisa, tarea por tarea, si las fechas respetan las dependencias declaradas.

    Fin→Inicio es un **mínimo**: arrancar más tarde que lo exigido no contradice
    nada (lo puede estar mandando otra predecesora). Lo que sí contradice es
    arrancar *antes*.
    """
    por_wbs = {f.wbs: f for f in importacion.filas if f.wbs}
    diagnostico = Diagnostico()

    for fila in importacion.filas:
        if not fila.inicio_declarado or not fila.wbs:
            continue
        requisitos = _requisitos(fila, por_wbs)
        if not requisitos:
            continue
        diagnostico.revisadas += 1
        diagnostico.discrepancias.extend(_revisar(fila, requisitos))

    return diagnostico


def _requisitos(
    fila: FilaImportada, por_wbs: dict[str, FilaImportada]
) -> list[tuple[str, FilaImportada, int, date]]:
    """Para cada predecesora Fin→Inicio: cuándo exige que arranque esta tarea."""
    salida = []
    for crudo in fila.predecesoras:
        referencia = parsear(crudo)
        if referencia is None:
            continue
        codigo, lag, tipo = referencia
        previa = por_wbs.get(codigo)
        if previa is None or not previa.fin_declarado or tipo.value != "FS":
            continue
        salto = 0 if previa.es_hito else 1
        salida.append((codigo, previa, lag, sumar_habiles(previa.fin_declarado, salto + lag)))
    return salida


def _revisar(
    fila: FilaImportada, requisitos: list[tuple[str, FilaImportada, int, date]]
) -> list[Discrepancia]:
    exigido = max(fecha for _, _, _, fecha in requisitos)
    declarado = fila.inicio_declarado

    if declarado == exigido:
        return []

    if declarado > exigido:
        hueco = _distancia_habil(exigido, declarado)
        if hueco < _HUECO_MINIMO:
            return []
        codigo = max(requisitos, key=lambda r: r[3])[0]
        return [
            Discrepancia(
                fila.wbs, fila.titulo, codigo, f"{codigo}+{hueco}",
                f"la planilla la arranca {hueco} días hábiles después de lo que exigen "
                f"sus dependencias: puede faltar una, o la fecha está puesta a mano",
                estructural=False,
            )
        ]

    # Arranca antes de lo permitido: acá sí hay una contradicción real.
    salida = []
    for codigo, previa, lag, fecha in requisitos:
        if declarado >= fecha:
            continue
        if declarado == previa.inicio_declarado:
            salida.append(Discrepancia(
                fila.wbs, fila.titulo, codigo, f"{codigo}SS",
                f"en la planilla arranca el mismo día que {codigo}, pero está declarada "
                "Fin→Inicio: es Inicio→Inicio",
            ))
        elif fila.fin_declarado and fila.fin_declarado == previa.fin_declarado:
            salida.append(Discrepancia(
                fila.wbs, fila.titulo, codigo, f"{codigo}FF",
                f"en la planilla termina el mismo día que {codigo}: es Fin→Fin",
            ))
        else:
            solape = _distancia_habil(declarado, fecha)
            # Un solape corto es fast-tracking deliberado y se puede declarar como
            # lag negativo. Uno enorme no: es la misma fecha a mano de siempre, y
            # convertirla en lag ancla el cronograma igual que un +104.
            salida.append(Discrepancia(
                fila.wbs, fila.titulo, codigo, f"{codigo}{lag - solape}",
                f"en la planilla se solapa {solape} días hábiles con {codigo}",
                estructural=solape <= _SOLAPE_CREIBLE,
            ))
    return salida


def _distancia_habil(desde: date, hasta: date) -> int:
    """Días hábiles con signo entre dos fechas."""
    if hasta >= desde:
        return contar_habiles(desde, hasta) - 1
    return -(contar_habiles(hasta, desde) - 1)


def aplicar_sugerencias(importacion: Importacion, diagnostico: Diagnostico) -> int:
    """Corrige **solo** las relaciones mal declaradas. Devuelve cuántas cambió.

    Las fechas puestas a mano quedan afuera a propósito: ver `Discrepancia`.
    """
    porfila: dict[str, dict[str, str]] = {}
    for d in diagnostico.estructurales:
        porfila.setdefault(d.wbs, {})[d.predecesora] = d.sugerencia

    cambios = 0
    for fila in importacion.filas:
        sugeridas = porfila.get(fila.wbs)
        if not sugeridas:
            continue
        nuevas = []
        for crudo in fila.predecesoras:
            referencia = parsear(crudo)
            codigo = referencia[0] if referencia else None
            if codigo in sugeridas:
                nuevas.append(sugeridas[codigo])
                cambios += 1
            else:
                nuevas.append(crudo)
        fila.predecesoras = nuevas
    return cambios
