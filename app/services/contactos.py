"""Las personas del proyecto. Resuelve texto libre contra una lista, sin fricción.

El problema que ataca: hasta acá el responsable era texto suelto en cada tarea, así
que «Ariel», «ariel» y «A. Clerici» eran tres personas y no había forma de preguntar
qué tiene asignado cada una.

La decisión de diseño está en `resolver`: la celda de la grilla **sigue siendo un
campo de texto**, no un desplegable. Escribís un nombre y se resuelve contra los
contactos que ya existen; si no está, se crea. Un desplegable obligaría a dar de alta
a la persona antes de poder escribirla, y con planillas de cuarenta filas eso se
abandona a la tercera. El resultado es el mismo —una fila por persona— sin pedirle
nada al usuario.
"""

from __future__ import annotations

import re
import unicodedata

from sqlmodel import Session, select

from ..models import Contacto, Project, Riesgo, Task

_ESPACIOS = re.compile(r"\s+")


def normalizar(nombre: str) -> str:
    """Clave de comparación: sin acentos, sin mayúsculas, sin espacios de más.

    Es lo único que decide si dos nombres son la misma persona. Deliberadamente
    simple: no intenta adivinar que «A. Clerici» y «Ariel Clerici» son lo mismo —
    eso lo une una persona desde la pantalla de equipo, no una heurística.
    """
    sin_acentos = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    return _ESPACIOS.sub(" ", sin_acentos).strip().casefold()[:120]


def listar(session: Session, project_id: int) -> list[Contacto]:
    contactos = list(session.exec(select(Contacto).where(Contacto.project_id == project_id)))
    contactos.sort(key=lambda c: c.nombre.casefold())
    return contactos


def obtener(session: Session, contacto_id: int) -> Contacto | None:
    return session.get(Contacto, contacto_id)


def buscar(session: Session, project_id: int, nombre: str) -> Contacto | None:
    clave = normalizar(nombre)
    if not clave:
        return None
    return next((c for c in listar(session, project_id) if c.clave == clave), None)


def resolver(session: Session, project_id: int, nombre: str) -> int | None:
    """Texto → id de contacto. Crea el contacto si el nombre es nuevo.

    Nombre vacío significa «sin asignar», que es distinto de un contacto llamado
    "" — por eso devuelve `None` en vez de crear una fila fantasma.
    """
    limpio = _ESPACIOS.sub(" ", nombre or "").strip()[:120]
    if not limpio:
        return None

    existente = buscar(session, project_id, limpio)
    if existente is not None:
        return existente.id

    contacto = Contacto(project_id=project_id, nombre=limpio, clave=normalizar(limpio))
    session.add(contacto)
    session.commit()
    session.refresh(contacto)
    return contacto.id


def renombrar(session: Session, contacto_id: int, nombre: str, mail: str = "") -> Contacto:
    contacto = session.get(Contacto, contacto_id)
    if contacto is None:
        raise ContactoInvalido("Ese contacto ya no existe")
    limpio = _ESPACIOS.sub(" ", nombre).strip()[:120]
    if not limpio:
        raise ContactoInvalido("El nombre no puede quedar vacío")

    choque = buscar(session, contacto.project_id, limpio)
    if choque is not None and choque.id != contacto_id:
        raise ContactoInvalido(
            f"Ya existe «{choque.nombre}» en este proyecto. Si son la misma persona, "
            "usá «Unir» en vez de renombrar."
        )

    contacto.nombre, contacto.clave = limpio, normalizar(limpio)
    contacto.mail = mail.strip()[:160]
    session.add(contacto)
    session.commit()
    session.refresh(contacto)
    return contacto


def unir(session: Session, origen_id: int, destino_id: int) -> int:
    """Pasa todo lo de `origen` a `destino` y borra el origen. Devuelve cuánto movió.

    Es la salida para lo que la normalización no puede resolver sola: «A. Clerici» y
    «Ariel Clerici» son la misma persona, pero eso lo sabe alguien, no un algoritmo.
    """
    origen = session.get(Contacto, origen_id)
    destino = session.get(Contacto, destino_id)
    if origen is None or destino is None or origen.project_id != destino.project_id:
        raise ContactoInvalido("Esos contactos no son del mismo proyecto")
    if origen_id == destino_id:
        raise ContactoInvalido("Es el mismo contacto")

    movidas = 0
    for tarea in session.exec(select(Task).where(Task.responsable_id == origen_id)):
        tarea.responsable_id = destino_id
        session.add(tarea)
        movidas += 1
    for proyecto in session.exec(select(Project).where(Project.responsable_id == origen_id)):
        proyecto.responsable_id = destino_id
        session.add(proyecto)
    for riesgo in session.exec(select(Riesgo).where(Riesgo.responsable_id == origen_id)):
        riesgo.responsable_id = destino_id
        session.add(riesgo)
    session.delete(origen)
    session.commit()
    return movidas


def eliminar(session: Session, contacto_id: int) -> None:
    """Borra el contacto y deja sus tareas sin asignar. No se pierde ninguna tarea."""
    contacto = session.get(Contacto, contacto_id)
    if contacto is None:
        return
    for tarea in session.exec(select(Task).where(Task.responsable_id == contacto_id)):
        tarea.responsable_id = None
        session.add(tarea)
    for proyecto in session.exec(select(Project).where(Project.responsable_id == contacto_id)):
        proyecto.responsable_id = None
        session.add(proyecto)
    for riesgo in session.exec(select(Riesgo).where(Riesgo.responsable_id == contacto_id)):
        riesgo.responsable_id = None
        session.add(riesgo)
    session.delete(contacto)
    session.commit()


def eliminar_del_proyecto(session: Session, project_id: int) -> None:
    for contacto in listar(session, project_id):
        session.delete(contacto)


def mapa(session: Session, project_id: int) -> dict[int, Contacto]:
    return {c.id: c for c in listar(session, project_id) if c.id is not None}


class ContactoInvalido(Exception):
    """Operación rechazada; el mensaje se le muestra al usuario."""
