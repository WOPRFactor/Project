"""Arma lo que la plantilla necesita: filas del árbol con fechas y barras del timeline.

Junta árbol + cronograma + grilla en una sola estructura para que el Jinja quede
tonto: iterar y pintar, sin calcular nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session

from ..engine.comparar import dias_habiles_con_signo
from ..engine.timeline import Extremo, Grilla, ancho_columna, barra, construir_grilla, flecha
from ..models import Dependency, Estado, Task
from . import dependencies as dependencies_service
from . import estados as estados_service
from . import gantt_vista
from . import pesos as pesos_service
from . import predecesoras as predecesoras_service
from . import resumen as resumen_service
from . import riesgos as riesgos_service
from . import schedule as schedule_service
from . import tasks as tasks_service
from .resumen import NivelAbierto, Resumen, esta_hecha  # noqa: F401 — API de la vista


@dataclass
class Fila:
    tarea: Task
    nivel: int
    es_resumen: bool
    # El estado ya no es un enum del código: es una fila del proyecto, y es quien
    # dice —vía `es_final`— si esta tarea cuenta como terminada.
    estado: Estado | None = None
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
    tiene_riesgo: bool = False
    # Contra la línea base vigente. Positivo = atrasada; None = sin base o sin fechas.
    desvio: int | None = None
    es_nueva: bool = False
    columnas_base: tuple[int, int] | None = None
    # Lo que la tarea vale sobre el proyecto entero. Derivado: se multiplica desde
    # la raíz, nunca se guarda. Lo que el usuario escribe es el % del padre.
    peso_absoluto: float = 0.0


@dataclass(frozen=True)
class Flecha:
    """Una conexión dibujable entre dos barras del timeline."""

    puntos: str
    tipo: str
    critica: bool
    titulo: str


@dataclass
class VistaProyecto:
    # `filas` es lo que se dibuja (puede venir filtrado); `todas_las_filas` es el
    # proyecto entero, y de ahí salen los totales. Filtrar la vista no puede cambiar
    # los números de arriba.
    filas: list[Fila]
    grilla: Grilla | None
    columna_hoy: int | None
    error: str | None
    todas_las_filas: list[Fila] = field(default_factory=list)
    estados: list[Estado] = field(default_factory=list)
    resumen: Resumen = field(default_factory=Resumen)
    por_ambito: list[Resumen] = field(default_factory=list)
    ventana: dict = field(default_factory=dict)
    estimadas: int = 0
    avance_ponderado: int = 0
    niveles_abiertos: list[NivelAbierto] = field(default_factory=list)
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


def armar(
    session: Session,
    project_id: int,
    hoy: date | None = None,
    mirada: gantt_vista.Mirada | None = None,
    base: dict[int, tuple] | None = None,
) -> VistaProyecto:
    """`base` son las fechas congeladas (`{task_id: (inicio, fin)}`), como dato plano:
    así el desvío se calcula acá sin que este módulo conozca la línea base."""
    cronograma, error = schedule_service.calcular_seguro(session, project_id)
    nodos = tasks_service.arbol(session, project_id)
    entrantes = dependencies_service.por_sucesora(session, project_id)

    grilla = None
    if cronograma.inicio is not None and cronograma.fin is not None:
        grilla = construir_grilla(cronograma.inicio, cronograma.fin)

    ancho = ancho_columna(grilla.columnas) if grilla else 22
    codigos = {t.id: t.codigo for t, _ in nodos}
    estados = estados_service.listar(session, project_id)
    por_estado = {e.id: e for e in estados}
    nodos_peso = [
        pesos_service.NodoPeso(t.id or 0, t.parent_id, t.peso, t.duracion)
        for t, _ in nodos
    ]
    peso_absoluto = pesos_service.absolutos(nodos_peso)
    con_riesgo = riesgos_service.ids_con_riesgo(session, project_id)
    base = base or {}
    filas: list[Fila] = []
    for tarea, nivel in nodos:
        calculada = cronograma.get(tarea.id or 0)
        propias = entrantes.get(tarea.id or 0, [])
        fila = Fila(
            tarea=tarea,
            nivel=nivel,
            es_resumen=bool(calculada and calculada.es_resumen),
            estado=por_estado.get(tarea.estado_id or 0),
            es_hito=tarea.duracion == 0,
            es_estimada=tarea.duracion_optimista is not None
            or tarea.duracion_pesimista is not None,
            predecesoras=propias,
            predecesoras_texto=_texto_predecesoras(propias, codigos),
            tiene_predecesoras=bool(propias),
            tiene_riesgo=(tarea.id or 0) in con_riesgo,
            peso_absoluto=peso_absoluto.get(tarea.id or 0, 0.0),
        )
        if calculada is not None:
            fila.inicio = calculada.inicio
            fila.fin = calculada.fin
            fila.holgura = calculada.holgura
            fila.sin_holgura = calculada.critica
            if grilla is not None:
                fila.columnas = barra(grilla, calculada.inicio, calculada.fin)
            _medir_desvio(fila, base, grilla)
        filas.append(fila)

    mirada = mirada or gantt_vista.Mirada()
    visibles = gantt_vista.filtrar(filas, mirada)

    return VistaProyecto(
        filas=visibles,
        todas_las_filas=filas,
        grilla=grilla,
        columna_hoy=grilla.columna_de(hoy or date.today()) if grilla else None,
        error=error,
        estados=estados,
        resumen=resumen_service.armar(filas, "Total", cronograma.inicio, cronograma.fin),
        por_ambito=resumen_service.por_ambito(filas),
        ventana=schedule_service.ventana(session, project_id),
        estimadas=len([f for f in filas if f.es_estimada and not f.es_resumen]),
        avance_ponderado=pesos_service.avance_ponderado(
            nodos_peso,
            {f.tarea.id or 0: f.estado.avance_sugerido if f.estado else 0 for f in filas},
        ),
        niveles_abiertos=resumen_service.niveles_abiertos(nodos_peso, filas),
        proximo_hito=resumen_service.proximo_hito(filas, hoy or date.today()),
        flechas=_flechas(visibles, dependencies_service.listar(session, project_id), ancho),
        ancho_dia=ancho,
    )


def _medir_desvio(fila: Fila, base: dict[int, tuple], grilla: Grilla | None) -> None:
    """Cuánto se movió esta fila desde que se congeló, y dónde iba la barra original."""
    if not base:
        return
    congelada = base.get(fila.tarea.id or 0)
    if congelada is None:
        # No estaba en la base: es alcance nuevo, no un atraso.
        fila.es_nueva = True
        return
    inicio_base, fin_base = congelada
    if fin_base is not None and fila.fin is not None:
        fila.desvio = dias_habiles_con_signo(fin_base, fila.fin)
    if grilla is not None and inicio_base is not None and fin_base is not None:
        fila.columnas_base = barra(grilla, inicio_base, fin_base)


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
