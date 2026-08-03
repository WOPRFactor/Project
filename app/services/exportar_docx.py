"""El plan y el informe como documento de Word editable.

Excepción al objetivo de 200 líneas (269, techo 300): son dos documentos que comparten
las mismas seis primitivas de Word. Partirlo dejaría un módulo de helpers de 90 líneas
sin responsabilidad propia, que es justo lo que la regla de modularizar por
responsabilidad —y no por conteo— busca evitar.

Existe además del PDF porque resuelven cosas distintas: el PDF es para **mandar** y sale
igual que la pantalla; el Word es para **retocar** —pegarle un párrafo de contexto,
sacarle una sección— antes de que salga con el nombre de uno.

**Sin Gantt, a propósito.** El Gantt de esta app es HTML y CSS; meterlo en un .docx
obligaría a redibujarlo con las formas de Word, y a partir de ahí el papel y la pantalla
empezarían a mostrar cosas distintas. Para el cronograma dibujado está el PDF. Acá van
las fechas en tabla, que además es lo que alguien va a querer editar.

Recibe los mismos objetos que las plantillas (`documento.Plan`, `informe.Informe`), así
los números salen del mismo cálculo que el tablero.
"""

from __future__ import annotations

import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

_VACIO = "—"


def del_plan(plan) -> bytes:
    """El plan de trabajo: resumen, bloques por ámbito y todas las tareas."""
    documento = Document()
    _apaisar(documento)
    documento.add_heading(plan.proyecto.nombre, level=0)
    _bajada(
        documento,
        f"Plan de trabajo al {_fecha(plan.hoy)}. "
        + (
            f"Medido contra la línea base «{plan.linea_base.nombre}»."
            if plan.hay_base
            else "Sin línea base congelada: son las fechas calculadas de hoy."
        ),
    )
    if plan.proyecto.descripcion:
        documento.add_paragraph(plan.proyecto.descripcion)
    for aviso in plan.avisos:
        _bajada(documento, aviso)

    documento.add_heading("Resumen", level=1)
    _lista(documento, [
        ("Arranque", _fecha(plan.resumen.inicio)),
        ("Fin proyectado", _fecha(plan.resumen.fin)),
        ("Duración", f"{plan.resumen.dias_habiles} días hábiles"),
        ("Tareas", f"{plan.resumen.tareas} ({plan.resumen.hitos} hitos)"),
        ("Avance", f"{plan.avance}% ponderado por peso"),
    ])
    if plan.proximo_hito:
        _lista(documento, [
            ("Próximo hito",
             f"{plan.proximo_hito.tarea.titulo} — {_fecha(plan.proximo_hito.fin)}"),
        ])

    if plan.por_ambito:
        documento.add_heading("Bloques", level=1)
        _tabla(
            documento,
            ["Bloque", "Ventana", "Días hábiles", "Esfuerzo"],
            [
                [
                    "Duración total" if indice == 0 else bloque.etiqueta,
                    f"{_fecha(bloque.inicio)} → {_fecha(bloque.fin)}",
                    str(bloque.dias_habiles),
                    f"{bloque.esfuerzo} d",
                ]
                for indice, bloque in enumerate(plan.por_ambito)
            ],
        )
        _bajada(
            documento,
            "Las ventanas son calendario y se superponen entre sí; el esfuerzo es "
            "trabajo acumulado. Son dos unidades distintas y no se suman.",
        )

    documento.add_heading(f"Tareas ({len(plan.filas)})", level=1)
    encabezados = ["WBS", "Tarea", "Resp.", "Predec.", "Días", "Inicio", "Fin"]
    if plan.hay_base:
        encabezados.append("Desvío")
    encabezados += ["Peso", "Avance", "Estado"]
    _tabla(documento, encabezados, [_fila_de_tarea(f, plan.hay_base) for f in plan.filas])
    _bajada(
        documento,
        "El cronograma dibujado va en la versión PDF: un Gantt no entra en un documento "
        "de texto sin volver a dibujarlo.",
    )
    return _bytes(documento)


def del_informe(informe) -> bytes:
    """El informe de estado a la fecha de corte."""
    documento = Document()
    documento.add_heading(f"Informe de estado — {informe.proyecto.nombre}", level=0)
    _bajada(
        documento,
        f"Al {_fecha(informe.corte)}. "
        + (
            f"Medido contra la línea base «{informe.linea_base.nombre}», congelada el "
            f"{_fecha(informe.linea_base.congelada_el)}."
            if informe.hay_base
            else "Sin línea base: se puede leer el estado, pero no el desvío."
        ),
    )

    documento.add_heading("Resumen ejecutivo", level=1)
    avance = f"{informe.avance_real}%"
    if informe.avance_planificado is not None:
        avance += (
            f" (planificado {informe.avance_planificado}%, "
            f"{informe.brecha:+d} puntos)"
        )
    datos = [("Avance", avance), ("Fin proyectado", _fecha(informe.resumen.fin))]
    if informe.hay_base:
        datos.append(
            ("Desvío", f"{informe.desvio_ambito.get('proyecto', 0):+d} días hábiles")
        )
    if informe.proximo_hito:
        datos.append(
            ("Próximo hito",
             f"{informe.proximo_hito.tarea.titulo} — {_fecha(informe.proximo_hito.fin)}")
        )
    _lista(documento, datos)

    _seccion_de_filas(
        documento, f"Atrasadas ({len(informe.atrasadas)})", informe.atrasadas,
        "Terminan más tarde que lo aprobado. La peor primero.", desvio=True,
    )
    _seccion_de_filas(
        documento, f"Sin margen ({len(informe.en_riesgo)})", informe.en_riesgo,
        "Todavía no pasó nada, pero no tienen holgura: cualquier demora acá mueve el "
        "fin de su bloque.",
    )

    if informe.hitos:
        documento.add_heading("Hitos", level=1)
        _tabla(
            documento,
            ["Hito", "Proyectado", "Estado"],
            [
                [f.tarea.titulo, _fecha(f.fin), f.estado.nombre if f.estado else _VACIO]
                for f in informe.hitos
            ],
        )

    riesgos = getattr(informe.riesgos, "riesgos", None) or []
    con_texto = [r for r in riesgos if r.descripcion]
    if con_texto:
        documento.add_heading("Riesgos", level=1)
        _tabla(
            documento,
            ["Riesgo", "P×I", "Mitigación"],
            [
                [r.descripcion, f"{r.probabilidad}×{r.impacto}", r.mitigacion or _VACIO]
                for r in con_texto[:15]
            ],
        )
    return _bytes(documento)


def _seccion_de_filas(documento, titulo, filas, nota, desvio=False) -> None:
    if not filas:
        return
    documento.add_heading(titulo, level=1)
    _bajada(documento, nota)
    encabezados = ["WBS", "Tarea", "Resp.", "Fin", "Avance"]
    if desvio:
        encabezados.insert(4, "Desvío")
    cuerpo = []
    for fila in filas[:20]:
        celdas = [
            fila.tarea.codigo, fila.tarea.titulo,
            fila.responsable.nombre if fila.responsable else _VACIO,
            _fecha(fila.fin),
        ]
        if desvio:
            celdas.append(f"{fila.desvio:+d} d")
        celdas.append(f"{fila.tarea.avance}%")
        cuerpo.append(celdas)
    _tabla(documento, encabezados, cuerpo)


def _fila_de_tarea(fila, hay_base: bool) -> list[str]:
    tarea = fila.tarea
    celdas = [
        tarea.codigo,
        # La sangría marca el nivel: en una tabla de Word no hay árbol.
        ("    " * fila.nivel) + ("◆ " if fila.es_hito else "") + tarea.titulo,
        fila.responsable.nombre if fila.responsable else _VACIO,
        fila.predecesoras_texto or _VACIO,
        _VACIO if fila.es_resumen else str(tarea.duracion),
        _fecha(fila.inicio),
        _fecha(fila.fin),
    ]
    if hay_base:
        celdas.append(_desvio(fila))
    celdas += [
        f"{fila.peso_absoluto:.1f}%",
        f"{tarea.avance}%",
        fila.estado.nombre if fila.estado else _VACIO,
    ]
    return celdas


def _desvio(fila) -> str:
    """Sin desvío hay dos motivos distintos, y no da lo mismo cuál: una tarea que no
    estaba en la línea base es alcance **nuevo**, no una tarea sin atraso."""
    if fila.desvio is not None:
        return f"{fila.desvio:+d}"
    return "nueva" if fila.es_nueva else _VACIO


def _tabla(documento, encabezados: list[str], filas: list[list[str]]) -> None:
    tabla = documento.add_table(rows=1, cols=len(encabezados))
    tabla.style = "Light Grid Accent 1"
    for celda, texto in zip(tabla.rows[0].cells, encabezados):
        celda.text = texto
        for parrafo in celda.paragraphs:
            for tramo in parrafo.runs:
                tramo.bold = True
    for fila in filas:
        celdas = tabla.add_row().cells
        for celda, texto in zip(celdas, fila):
            celda.text = texto
    _achicar(tabla)


def _achicar(tabla) -> None:
    """Cuerpo chico: una tabla de diez columnas con la letra por defecto no entra."""
    for fila in tabla.rows:
        for celda in fila.cells:
            for parrafo in celda.paragraphs:
                for tramo in parrafo.runs:
                    tramo.font.size = Pt(7.5)


def _lista(documento, pares: list[tuple[str, str]]) -> None:
    for etiqueta, valor in pares:
        parrafo = documento.add_paragraph(style="List Bullet")
        parrafo.add_run(f"{etiqueta}: ").bold = True
        parrafo.add_run(valor)


def _bajada(documento, texto: str) -> None:
    parrafo = documento.add_paragraph()
    tramo = parrafo.add_run(texto)
    tramo.italic = True
    tramo.font.size = Pt(9)
    parrafo.alignment = WD_ALIGN_PARAGRAPH.LEFT


def _apaisar(documento) -> None:
    """Hoja horizontal: la tabla del plan tiene once columnas."""
    from docx.enum.section import WD_ORIENT

    for seccion in documento.sections:
        ancho, alto = seccion.page_width, seccion.page_height
        if ancho < alto:
            seccion.orientation = WD_ORIENT.LANDSCAPE
            seccion.page_width, seccion.page_height = alto, ancho


def _fecha(valor) -> str:
    return valor.strftime("%d/%m/%Y") if valor else _VACIO


def _bytes(documento) -> bytes:
    memoria = io.BytesIO()
    documento.save(memoria)
    return memoria.getvalue()
