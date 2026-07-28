"""Peso de cada tarea dentro del proyecto. Módulo puro: no toca la base ni la sesión.

**El peso se declara como % del padre, no del proyecto.** Es la decisión central de
este archivo. Si cada tarea guardara su porcentaje absoluto, agregar una sola tarea
en cualquier rincón del árbol rompería la suma de todo lo demás. Declarándolo contra
el padre, cada nivel cierra por su cuenta y agregar una tarea solo obliga a
rebalancear a sus hermanas. El peso absoluto —lo que la tarea vale en el proyecto—
es un dato *derivado*: se obtiene multiplicando hacia abajo desde la raíz.

El peso es opcional. `None` significa "repartí en partes iguales lo que sobre entre
las hermanas que tampoco lo declararon", así un nivel que nadie tocó queda parejo
solo y no le pide nada al usuario.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NodoPeso:
    """Lo mínimo que hace falta para repartir: quién cuelga de quién y qué declaró."""

    id: int
    parent_id: int | None = None
    peso: int | None = None
    duracion: int = 1


@dataclass(frozen=True)
class Nivel:
    """Un grupo de hermanas y el estado de su cuenta."""

    parent_id: int | None
    declarado: int
    sin_declarar: int

    @property
    def cierra(self) -> bool:
        """Con hermanas en blanco, cualquier declaración hasta 100 se completa sola."""
        if self.sin_declarar:
            return self.declarado <= 100
        return self.declarado == 100

    @property
    def diferencia(self) -> int:
        """Cuánto falta (negativo) o cuánto sobra (positivo) para llegar a 100."""
        return self.declarado - 100

    @property
    def sin_reparto(self) -> bool:
        """Hay hermanas en blanco pero no queda nada para darles: van a pesar 0."""
        return bool(self.sin_declarar) and self.declarado >= 100


def repartir(declarados: list[int | None]) -> list[float]:
    """Pesos efectivos de un grupo de hermanas, en % del padre y sumando 100.

    Siempre devuelve una repartición que suma 100, incluso cuando lo declarado no
    cierra: un nivel cargado al 120 se normaliza en vez de producir un avance del
    120%. Que la cuenta no cierre se avisa por otro lado (`niveles`), no deformando
    el número acá.
    """
    if not declarados:
        return []

    suma = sum(d for d in declarados if d is not None)
    en_blanco = [i for i, d in enumerate(declarados) if d is None]
    cuota = max(0.0, 100.0 - suma) / len(en_blanco) if en_blanco else 0.0

    efectivos = [float(d) if d is not None else cuota for d in declarados]
    total = sum(efectivos)
    if total <= 0:
        return [100.0 / len(declarados)] * len(declarados)
    return [valor * 100.0 / total for valor in efectivos]


def niveles(nodos: list[NodoPeso]) -> list[Nivel]:
    """Un `Nivel` por grupo de hermanas, para poder avisar cuál no cierra."""
    grupos: dict[int | None, list[NodoPeso]] = {}
    for nodo in nodos:
        grupos.setdefault(nodo.parent_id, []).append(nodo)

    return [
        Nivel(
            parent_id=padre,
            declarado=sum(n.peso for n in hermanas if n.peso is not None),
            sin_declarar=len([n for n in hermanas if n.peso is None]),
        )
        for padre, hermanas in grupos.items()
    ]


def absolutos(nodos: list[NodoPeso]) -> dict[int, float]:
    """Peso de cada tarea sobre el proyecto entero, multiplicando desde la raíz."""
    grupos: dict[int | None, list[NodoPeso]] = {}
    for nodo in nodos:
        grupos.setdefault(nodo.parent_id, []).append(nodo)

    salida: dict[int, float] = {}
    pendientes: list[tuple[int | None, float]] = [(None, 100.0)]
    while pendientes:
        padre, disponible = pendientes.pop()
        hermanas = grupos.get(padre, [])
        for hermana, porcion in zip(hermanas, repartir([h.peso for h in hermanas])):
            propio = disponible * porcion / 100.0
            salida[hermana.id] = propio
            if hermana.id in grupos:
                pendientes.append((hermana.id, propio))
    return salida


def hojas(nodos: list[NodoPeso]) -> set[int]:
    con_hijas = {n.parent_id for n in nodos if n.parent_id is not None}
    return {n.id for n in nodos if n.id not in con_hijas}


def avance_ponderado(nodos: list[NodoPeso], avances: dict[int, int]) -> int:
    """Avance del proyecto pesando cada tarea por lo que vale, no contando cabezas.

    Es la razón de ser del peso: sin esto una firma de acta de un día cuenta lo mismo
    que ciento veinte días de acompañamiento.
    """
    if not nodos:
        return 0
    peso = absolutos(nodos)
    return round(sum(
        peso.get(id_, 0.0) * avances.get(id_, 0) / 100.0 for id_ in hojas(nodos)
    ))


def repartir_parejo(cuantas: int) -> list[int]:
    """Punto de partida: todas iguales. Los redondeos van a las primeras."""
    if cuantas <= 0:
        return []
    base, resto = divmod(100, cuantas)
    return [base + (1 if i < resto else 0) for i in range(cuantas)]


def repartir_por_duracion(duraciones: list[int]) -> list[int]:
    """Punto de partida alternativo: lo que más tarda, más pesa.

    Es un *arranque*, no una respuesta: el valor de negocio no es proporcional al
    tiempo, y por eso el peso lo termina decidiendo una persona. Con todo en cero
    (o solo hitos) cae en el reparto parejo.
    """
    total = sum(max(0, d) for d in duraciones)
    if total <= 0:
        return repartir_parejo(len(duraciones))

    crudos = [max(0, d) * 100 / total for d in duraciones]
    enteros = [int(valor) for valor in crudos]
    # El faltante por redondeo va a las que más parte decimal perdieron.
    orden = sorted(range(len(crudos)), key=lambda i: crudos[i] - enteros[i], reverse=True)
    for i in orden[: 100 - sum(enteros)]:
        enteros[i] += 1
    return enteros
