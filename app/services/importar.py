"""Contratos del import: qué filas entrarían y qué avisos hay que mirar.

Un import es un dato en dos partes: las filas que se van a crear y los **avisos**
sobre lo que hubo que arreglar o saltear. Nada se repara en silencio.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date


TIPOS = {"fase", "tarea", "hito"}


@dataclass
class FilaImportada:
    """Una fila lista para convertirse en tarea."""

    titulo: str
    wbs: str = ""
    tipo: str = "tarea"
    duracion: int = 1
    responsable: str = ""
    critica: bool = False
    ambito: str = "proyecto"
    # % del padre; None = se reparte solo. Ver `services/pesos.py`.
    peso: int | None = None
    duracion_optimista: int | None = None
    duracion_pesimista: int | None = None
    predecesoras: list[str] = field(default_factory=list)
    nivel: int = 0
    # Fechas que trae la planilla. No se importan (las calcula el motor), pero
    # sirven para detectar cuándo contradicen a las dependencias declaradas.
    inicio_declarado: date | None = None
    fin_declarado: date | None = None

    @property
    def es_hito(self) -> bool:
        return self.tipo == "hito"


@dataclass
class Importacion:
    """Resultado de leer una fuente: qué se importaría y qué hay que mirar."""

    filas: list[FilaImportada] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    origen: str = ""

    @property
    def resumen(self) -> str:
        cuenta: dict[str, int] = {}
        for fila in self.filas:
            cuenta[fila.tipo] = cuenta.get(fila.tipo, 0) + 1
        partes = [f"{cuenta[t]} {t}{'s' if cuenta[t] > 1 else ''}" for t in sorted(cuenta)]
        vinculos = sum(len(f.predecesoras) for f in self.filas)
        return f"{len(self.filas)} filas ({', '.join(partes)}) y {vinculos} dependencias"


MAX_FILAS = 2000
MAX_PREDECESORAS = 50


def a_json(importacion: Importacion) -> str:
    """Serializa la previsualización para que viaje en un campo oculto del formulario."""
    crudas = []
    for fila in importacion.filas:
        datos = asdict(fila)
        for campo in ("inicio_declarado", "fin_declarado"):
            valor = datos.get(campo)
            datos[campo] = valor.isoformat() if valor else None
        crudas.append(datos)
    return json.dumps(crudas, ensure_ascii=False)


def desde_json(carga: str) -> Importacion | None:
    """Reconstruye la previsualización que vuelve del navegador.

    Viene del cliente, así que se trata como input externo: tipos estrictos,
    longitudes acotadas y descarte de todo lo que no encaje. Después, cada tarea
    y cada dependencia pasa igual por la validación de siempre.
    """
    try:
        crudas = json.loads(carga)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(crudas, list) or len(crudas) > MAX_FILAS:
        return None

    importacion = Importacion(origen="previsualización confirmada")
    for cruda in crudas:
        if not isinstance(cruda, dict):
            continue
        titulo = str(cruda.get("titulo", "")).strip()[:200]
        if not titulo:
            continue
        tipo = cruda.get("tipo")
        predecesoras = cruda.get("predecesoras")
        importacion.filas.append(
            FilaImportada(
                titulo=titulo,
                wbs=str(cruda.get("wbs", ""))[:40],
                tipo=tipo if tipo in TIPOS else "tarea",
                duracion=_entero(cruda.get("duracion"), 1, 0, 3650),
                responsable=str(cruda.get("responsable", ""))[:120],
                critica=cruda.get("critica") is True,
                ambito=_ambito(cruda.get("ambito")),
                peso=_opcional(cruda.get("peso"), 0, 100),
                duracion_optimista=_opcional(cruda.get("duracion_optimista"), 0, 3650),
                duracion_pesimista=_opcional(cruda.get("duracion_pesimista"), 0, 3650),
                predecesoras=[
                    str(p)[:40]
                    for p in (predecesoras if isinstance(predecesoras, list) else [])
                ][:MAX_PREDECESORAS],
                nivel=_entero(cruda.get("nivel"), 0, 0, 20),
                inicio_declarado=_fecha(cruda.get("inicio_declarado")),
                fin_declarado=_fecha(cruda.get("fin_declarado")),
            )
        )
    return importacion


AMBITOS = {"proyecto", "seguimiento", "control"}


def _ambito(valor) -> str:
    """Enum cerrado: lo que no esté en la lista cae en el ámbito por defecto."""
    texto = str(valor).strip().lower() if valor is not None else ""
    return texto if texto in AMBITOS else "proyecto"


def _opcional(valor, minimo: int, maximo: int) -> int | None:
    """Un entero acotado, o None si no vino: None y cero significan cosas distintas."""
    if valor is None or valor == "":
        return None
    try:
        return max(minimo, min(int(valor), maximo))
    except (TypeError, ValueError):
        return None


def _fecha(valor) -> date | None:
    try:
        return date.fromisoformat(valor) if isinstance(valor, str) else None
    except ValueError:
        return None


def _entero(valor, default: int, minimo: int, maximo: int) -> int:
    try:
        return max(minimo, min(int(valor), maximo))
    except (TypeError, ValueError):
        return default
