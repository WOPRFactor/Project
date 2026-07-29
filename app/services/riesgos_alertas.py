"""Lo que el registro de riesgos te avisa. Módulo puro: sin base ni sesión.

Un registro de riesgos se pudre solo. La forma típica: se cargan veinte riesgos en
la reunión de arranque, nadie define qué se va a hacer con ellos, y seis meses
después la planilla sigue igual mientras dos ya se materializaron. Lo que lo
mantiene vivo no es el cuadrante —que es una foto— sino estas preguntas.

Todas **avisan, no bloquean**: un riesgo a medio cargar es un estado legítimo,
frenar la carga sería la forma más rápida de que nadie cargue riesgos.

Los cerrados quedan afuera de todo: ya no hay nada que hacer con ellos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..models import RESPUESTAS_ACTIVAS, EstadoRiesgo, Respuesta, Riesgo


@dataclass(frozen=True)
class Alerta:
    """Un pendiente del registro, con los riesgos que lo tienen."""

    clave: str
    mensaje: str
    riesgos: tuple[int, ...]
    grave: bool = False

    @property
    def cuantos(self) -> int:
        return len(self.riesgos)


# Severidad desde la cual un riesgo pide atención explícita. Es el piso de la zona
# crítica de la matriz 5×5 (ver `services/matriz.zona`).
CRITICO = 15


def _sin_respuesta(riesgo: Riesgo, hoy: date) -> bool:
    return riesgo.respuesta == Respuesta.sin_definir


def _sin_plan_escrito(riesgo: Riesgo, hoy: date) -> bool:
    """Decidir «mitigar» sin escribir qué se hace es no haber decidido nada."""
    return riesgo.respuesta in RESPUESTAS_ACTIVAS and not riesgo.mitigacion.strip()


def _sin_residual(riesgo: Riesgo, hoy: date) -> bool:
    return riesgo.respuesta in RESPUESTAS_ACTIVAS and not riesgo.residual_declarado


def _residual_peor(riesgo: Riesgo, hoy: date) -> bool:
    return riesgo.residual_declarado and riesgo.severidad_residual > riesgo.severidad


def _plan_sin_efecto(riesgo: Riesgo, hoy: date) -> bool:
    return (
        riesgo.respuesta in RESPUESTAS_ACTIVAS
        and riesgo.residual_declarado
        and riesgo.severidad_residual == riesgo.severidad
    )


def _revision_vencida(riesgo: Riesgo, hoy: date) -> bool:
    return riesgo.revisar_el is not None and riesgo.revisar_el < hoy


def _grave_sin_revision(riesgo: Riesgo, hoy: date) -> bool:
    return riesgo.revisar_el is None and riesgo.severidad_residual >= CRITICO


def _materializado(riesgo: Riesgo, hoy: date) -> bool:
    return riesgo.estado == EstadoRiesgo.materializado


def _sin_disparador(riesgo: Riesgo, hoy: date) -> bool:
    return not riesgo.disparador.strip() and riesgo.severidad_residual >= CRITICO


# Orden de lectura: primero lo que ya pasó, después lo que falta decidir.
#
# Los mensajes se escriben como frase sin verbo —«con la revisión vencida»— y no como
# oración: la pantalla los antepone con el conteo («3 riesgos …»), y así uno y varios
# se leen igual sin tener que guardar dos redacciones.
_CONTROLES = (
    ("materializado", _materializado, True,
     "ya materializados: eso no es un riesgo, es un problema, y debería tener "
     "su tarea en el cronograma"),
    ("revision_vencida", _revision_vencida, True,
     "con la fecha de revisión vencida"),
    ("residual_peor", _residual_peor, True,
     "con el residual peor que el inherente: el residual es *después* del plan, "
     "revisá los números"),
    ("sin_respuesta", _sin_respuesta, False,
     "sin definir qué se va a hacer con ellos"),
    ("sin_plan_escrito", _sin_plan_escrito, False,
     "con una respuesta activa que no dice en qué consiste"),
    ("sin_residual", _sin_residual, False,
     "sin estimar cuánto baja el plan: así no hay con qué comparar"),
    ("plan_sin_efecto", _plan_sin_efecto, False,
     "con un plan que los deja igual que antes"),
    ("grave_sin_revision", _grave_sin_revision, False,
     "en zona crítica sin fecha de revisión"),
    ("sin_disparador", _sin_disparador, False,
     "en zona crítica sin disparador: no hay qué mirar para saber si están pasando"),
)


def revisar(riesgos: list[Riesgo], hoy: date | None = None) -> list[Alerta]:
    """Los pendientes del registro, más grave primero. Lista vacía = está al día."""
    hoy = hoy or date.today()
    vivos = [r for r in riesgos if r.estado != EstadoRiesgo.cerrado]
    salida = []
    for clave, control, grave, mensaje in _CONTROLES:
        afectados = tuple(r.id or 0 for r in vivos if control(r, hoy))
        if afectados:
            salida.append(Alerta(clave, mensaje, afectados, grave))
    return salida


def al_dia(riesgos: list[Riesgo], hoy: date | None = None) -> bool:
    return not revisar(riesgos, hoy)
