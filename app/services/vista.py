"""Arma lo que la plantilla necesita: filas del árbol con fechas y barras del timeline.

Junta árbol + cronograma + grilla en una sola estructura para que el Jinja quede
tonto: iterar y pintar, sin calcular nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session

from ..engine.calendar import contar_habiles
from ..engine.timeline import Extremo, Grilla, ancho_columna, barra, construir_grilla, flecha
from ..models import ETIQUETA_AMBITO, Ambito, Dependency, Task
from . import dependencies as dependencies_service
from . import predecesoras as predecesoras_service
from . import schedule as schedule_service
from . import tasks as tasks_service


@dataclass
class Fila:
    tarea: Task
    nivel: int
    es_resumen: bool
    es_hito: bool = False
    inicio: date | None = None
    fin: date | None = None
    holgura: int = 0
    # Ruta crítica según el motor (holgura cero). Distinta de `tarea.critica`,
    # que es la criticidad de negocio que marca el usuario.
    sin_holgura: bool = False
    columnas: tuple[int, int] | None = None
    predecesoras: list[Dependency] | None = None
    predecesoras_texto: str = ""
    tiene_predecesoras: bool = False
    es_estimada: bool = False


@dataclass(frozen=True)
class Flecha:
    """Una conexión dibujable entre dos barras del timeline."""

    puntos: str
    tipo: str
    critica: bool
    titulo: str


@dataclass
class Resumen:
    """Cuánto dura un bloque de tareas según el cronograma de este momento.

    Hay uno por ámbito más el total: el acompañamiento posterior no tiene por qué
    inflar la duración del alcance comprometido, pero tampoco desaparecer.
    """

    etiqueta: str = "Total"
    inicio: date | None = None
    fin: date | None = None
    dias_habiles: int = 0
    dias_corridos: int = 0
    tareas: int = 0
    hitos: int = 0
    hechas: int = 0
    # Suma de las duraciones de las tareas del bloque. Es *trabajo*, no calendario:
    # tareas en paralelo suman acá pero no estiran la ventana.
    esfuerzo: int = 0

    @property
    def semanas(self) -> int:
        return -(-self.dias_habiles // 5)  # redondeo hacia arriba

    @property
    def avance(self) -> int:
        return round(100 * self.hechas / self.tareas) if self.tareas else 0


@dataclass
class VistaProyecto:
    filas: list[Fila]
    grilla: Grilla | None
    columna_hoy: int | None
    error: str | None
    resumen: Resumen = field(default_factory=Resumen)
    por_ambito: list[Resumen] = field(default_factory=list)
    ventana: dict = field(default_factory=dict)
    estimadas: int = 0
    proximo_hito: Fila | None = None
    flechas: list[Flecha] = field(default_factory=list)
    ancho_dia: int = 22
    alto_fila: int = 32
    alto_cabecera: int = 44

    @property
    def alto_pista(self) -> int:
        return self.alto_cabecera + len(self.filas) * self.alto_fila


def _texto_predecesoras(deps: list[Dependency], codigos: dict[int, str]) -> str:
    """Lo que se ve en la celda: `1.3, 2.1SS+2`."""
    partes = [
        predecesoras_service.escribir(
            codigos.get(d.predecessor_id) or str(d.predecessor_id), d.lag, d.tipo
        )
        for d in deps
    ]
    return ", ".join(sorted(partes))


def armar(session: Session, project_id: int, hoy: date | None = None) -> VistaProyecto:
    cronograma, error = schedule_service.calcular_seguro(session, project_id)
    nodos = tasks_service.arbol(session, project_id)
    entrantes = dependencies_service.por_sucesora(session, project_id)

    grilla = None
    if cronograma.inicio is not None and cronograma.fin is not None:
        grilla = construir_grilla(cronograma.inicio, cronograma.fin)

    ancho = ancho_columna(grilla.columnas) if grilla else 22
    codigos = {t.id: t.codigo for t, _ in nodos}
    filas: list[Fila] = []
    for tarea, nivel in nodos:
        calculada = cronograma.get(tarea.id or 0)
        propias = entrantes.get(tarea.id or 0, [])
        fila = Fila(
            tarea=tarea,
            nivel=nivel,
            es_resumen=bool(calculada and calculada.es_resumen),
            es_hito=tarea.duracion == 0,
            es_estimada=tarea.duracion_optimista is not None
            or tarea.duracion_pesimista is not None,
            predecesoras=propias,
            predecesoras_texto=_texto_predecesoras(propias, codigos),
            tiene_predecesoras=bool(propias),
        )
        if calculada is not None:
            fila.inicio = calculada.inicio
            fila.fin = calculada.fin
            fila.holgura = calculada.holgura
            fila.sin_holgura = calculada.critica
            if grilla is not None:
                fila.columnas = barra(grilla, calculada.inicio, calculada.fin)
        filas.append(fila)

    return VistaProyecto(
        filas=filas,
        grilla=grilla,
        columna_hoy=grilla.columna_de(hoy or date.today()) if grilla else None,
        error=error,
        resumen=_resumir(filas, "Total", cronograma.inicio, cronograma.fin),
        por_ambito=_por_ambito(filas),
        ventana=schedule_service.ventana(session, project_id),
        estimadas=len([f for f in filas if f.es_estimada and not f.es_resumen]),
        proximo_hito=_proximo_hito(filas, hoy or date.today()),
        flechas=_flechas(filas, dependencies_service.listar(session, project_id), ancho),
        ancho_dia=ancho,
    )


_ALTO_FILA = 32
_ALTO_CABECERA = 44


def _flechas(filas: list[Fila], dependencias, ancho_dia: int) -> list[Flecha]:
    """Une cada barra con las que dependen de ella. Sin barra pintada, no hay flecha."""
    ubicacion = {
        f.tarea.id: (i, f)
        for i, f in enumerate(filas)
        if f.columnas is not None
    }
    salida: list[Flecha] = []
    for dep in dependencias:
        origen = ubicacion.get(dep.predecessor_id)
        destino = ubicacion.get(dep.successor_id)
        if origen is None or destino is None:
            continue
        (i_previa, previa), (i_sucesora, sucesora) = origen, destino
        salida.append(Flecha(
            puntos=flecha(
                dep.tipo.value,
                Extremo(previa.columnas[0], previa.columnas[1], i_previa),
                Extremo(sucesora.columnas[0], sucesora.columnas[1], i_sucesora),
                ancho_dia, _ALTO_FILA, _ALTO_CABECERA,
            ),
            tipo=dep.tipo.value,
            critica=previa.sin_holgura and sucesora.sin_holgura,
            titulo=f"{previa.tarea.titulo} → {sucesora.tarea.titulo}",
        ))
    return salida


def _proximo_hito(filas: list[Fila], hoy: date) -> Fila | None:
    """El primer hito que todavía no pasó. Es lo que se mira un martes a la mañana."""
    pendientes = [
        f for f in filas
        if f.es_hito and f.fin and f.fin >= hoy and f.tarea.estado.value != "hecha"
    ]
    if pendientes:
        return min(pendientes, key=lambda f: f.fin)
    futuros = [f for f in filas if f.es_hito and f.fin]
    return max(futuros, key=lambda f: f.fin) if futuros else None


def _por_ambito(filas: list[Fila]) -> list[Resumen]:
    """Un contador por ámbito que tenga tareas, en el orden del enum."""
    salida = []
    for ambito in Ambito:
        del_ambito = [f for f in filas if not f.es_resumen and f.tarea.ambito == ambito]
        if not del_ambito:
            continue
        fechas = [(f.inicio, f.fin) for f in del_ambito if f.inicio and f.fin]
        if not fechas:
            continue
        salida.append(_resumir(
            del_ambito,
            ETIQUETA_AMBITO[ambito],
            min(i for i, _ in fechas),
            max(f for _, f in fechas),
        ))
    return salida


def _resumir(
    filas: list[Fila], etiqueta: str, inicio: date | None, fin: date | None
) -> Resumen:
    """Duración de un bloque: se recalcula sola al agregar o quitar tareas."""
    hojas = [f for f in filas if not f.es_resumen]
    return Resumen(
        etiqueta=etiqueta,
        inicio=inicio,
        fin=fin,
        dias_habiles=contar_habiles(inicio, fin) if inicio and fin else 0,
        dias_corridos=(fin - inicio).days + 1 if inicio and fin else 0,
        tareas=len([f for f in hojas if not f.es_hito]),
        hitos=len([f for f in hojas if f.es_hito]),
        hechas=len([f for f in hojas if f.tarea.estado.value == "hecha"]),
        esfuerzo=sum(f.tarea.duracion for f in hojas),
    )
