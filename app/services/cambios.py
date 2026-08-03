"""Historial de cambios: lo escriben los services, nadie lo edita (Fase 12).

La forma de trabajar es sacarle una **foto** a la tarea antes de tocarla y otra
después, y anotar las diferencias. Es más simple y más difícil de olvidar que hacer
que cada campo avise por su cuenta, y de paso el historial queda con los nombres que
el usuario ve en la grilla en vez de con nombres de columnas.

La foto guarda texto ya resuelto, no ids: ver el porqué en `models_cambio`.
"""

from __future__ import annotations

from sqlmodel import Session, select

from ..models import ETIQUETA_AMBITO, Task
from ..models_auth import Usuario
from ..models_cambio import Cambio
from . import contactos as contactos_service
from . import estados as estados_service

# Los campos que se auditan, con la etiqueta que tienen en la grilla. El orden es el
# de las columnas, así el historial se lee en el mismo idioma que la pantalla.
CAMPOS: list[tuple[str, str]] = [
    ("codigo", "WBS"),
    ("titulo", "Tarea"),
    ("responsable_id", "Resp."),
    ("duracion", "Días"),
    ("duracion_optimista", "Opt."),
    ("duracion_pesimista", "Pes."),
    ("snet", "No antes de"),
    ("critica", "Crít."),
    ("peso", "Peso"),
    ("avance", "Avance"),
    ("estado_id", "Estado"),
    ("ambito", "Ámbito"),
    ("parent_id", "Cuelga de"),
    ("notas", "Notas"),
]

CAMPO_TAREA = "Tarea"
ALTA = "Creada"
BAJA = "Borrada"
EXISTIA = "Existía"

_VACIO = "—"
# Lo que entra en la columna; el resto se corta con puntos suspensivos.
_TOPE = 250


def etiqueta_de(tarea: Task) -> str:
    partes = [p for p in (tarea.codigo, tarea.titulo) if p]
    return _cortar(" · ".join(partes) or f"tarea {tarea.id}")


def foto(session: Session, tarea: Task) -> dict[str, str]:
    """Cómo se ve la tarea ahora, campo por campo y ya en texto legible."""
    return {
        etiqueta: _valor(session, tarea, campo) for campo, etiqueta in CAMPOS
    }


def registrar_diferencias(
    session: Session,
    tarea: Task,
    antes: dict[str, str],
    usuario_id: int | None = None,
) -> int:
    """Anota lo que cambió entre `antes` y el estado actual de la tarea."""
    despues = foto(session, tarea)
    anotados = 0
    for _campo, etiqueta in CAMPOS:
        viejo, nuevo = antes.get(etiqueta, _VACIO), despues.get(etiqueta, _VACIO)
        if viejo == nuevo:
            continue
        anotar(session, tarea, etiqueta, viejo, nuevo, usuario_id)
        anotados += 1
    if anotados:
        session.commit()
    return anotados


def anotar(
    session: Session,
    tarea: Task,
    campo: str,
    antes: str,
    despues: str,
    usuario_id: int | None = None,
) -> None:
    """Deja el cambio listo en la sesión **sin** confirmar.

    Existe aparte de `registrar` para las operaciones que tocan muchas filas de una
    (renumerar): un commit por fila convertiría una acción en cincuenta.
    """
    if antes == despues:
        return
    session.add(
        Cambio(
            project_id=tarea.project_id,
            task_id=tarea.id,
            usuario_id=usuario_id,
            etiqueta=etiqueta_de(tarea),
            campo=campo,
            antes=_cortar(antes),
            despues=_cortar(despues),
        )
    )


def registrar(
    session: Session,
    tarea: Task,
    campo: str,
    antes: str,
    despues: str,
    usuario_id: int | None = None,
) -> None:
    """Un cambio que no sale de comparar dos fotos: el alta, la baja, las predecesoras."""
    if antes == despues:
        return
    anotar(session, tarea, campo, antes, despues, usuario_id)
    session.commit()


def listar(
    session: Session,
    project_id: int,
    task_id: int | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
) -> tuple[list[Cambio], int]:
    """Los cambios del proyecto, del más nuevo al más viejo. Devuelve (filas, total)."""
    condiciones = [Cambio.project_id == project_id]
    if task_id is not None:
        condiciones.append(Cambio.task_id == task_id)

    todos = list(
        session.exec(
            select(Cambio).where(*condiciones).order_by(Cambio.cuando.desc(), Cambio.id.desc())
        )
    )
    pagina = max(1, pagina)
    desde = (pagina - 1) * por_pagina
    return todos[desde : desde + por_pagina], len(todos)


def nombres_de_usuarios(session: Session, cambios: list[Cambio]) -> dict[int, str]:
    """Para mostrar quién, sin una consulta por fila."""
    ids = {c.usuario_id for c in cambios if c.usuario_id is not None}
    if not ids:
        return {}
    cuentas = session.exec(select(Usuario).where(Usuario.id.in_(ids)))
    return {c.id: (c.nombre or c.mail) for c in cuentas if c.id is not None}


# Los campos que no se leen solos: un id hay que resolverlo y un booleano o un
# porcentaje se escriben como los diría una persona. El resto cae en `str()`.
_LECTORES = {
    "responsable_id": lambda s, t: _nombre_de_contacto(s, t),
    "estado_id": lambda s, t: _nombre_de_estado(s, t),
    "parent_id": lambda s, t: _nombre_de_padre(s, t),
    "critica": lambda _s, t: "Sí" if t.critica else "No",
    "ambito": lambda _s, t: ETIQUETA_AMBITO.get(t.ambito, str(t.ambito)),
    "peso": lambda _s, t: _VACIO if t.peso is None else f"{t.peso}%",
    "avance": lambda _s, t: f"{t.avance}%",
    "snet": lambda _s, t: t.snet.isoformat() if t.snet else _VACIO,
}


def _valor(session: Session, tarea: Task, campo: str) -> str:
    lector = _LECTORES.get(campo)
    if lector is not None:
        return lector(session, tarea)
    valor = getattr(tarea, campo, None)
    if valor is None or valor == "":
        return _VACIO
    return _cortar(str(valor))


def _nombre_de_contacto(session: Session, tarea: Task) -> str:
    if tarea.responsable_id is None:
        return _VACIO
    contacto = contactos_service.obtener(session, tarea.responsable_id)
    return contacto.nombre if contacto else _VACIO


def _nombre_de_estado(session: Session, tarea: Task) -> str:
    if tarea.estado_id is None:
        return _VACIO
    estado = estados_service.obtener(session, tarea.estado_id)
    return estado.nombre if estado else _VACIO


def _nombre_de_padre(session: Session, tarea: Task) -> str:
    if tarea.parent_id is None:
        return "Raíz"
    padre = session.get(Task, tarea.parent_id)
    return etiqueta_de(padre) if padre else _VACIO


def _cortar(texto: str) -> str:
    return texto if len(texto) <= _TOPE else texto[: _TOPE - 1] + "…"


__all__ = [
    "ALTA",
    "BAJA",
    "CAMPOS",
    "CAMPO_TAREA",
    "EXISTIA",
    "anotar",
    "etiqueta_de",
    "foto",
    "listar",
    "nombres_de_usuarios",
    "registrar",
    "registrar_diferencias",
]
