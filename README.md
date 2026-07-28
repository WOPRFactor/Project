# WOPR Proyectos

Planificador de proyectos local, estilo MS Project pero propio: árbol de tareas con
subtareas, dependencias Fin→Inicio con lag, y un timeline semanal con las fechas
**calculadas** por un motor de scheduling.

Corre solo en `127.0.0.1`, un usuario, sin auth. Los datos viven en un SQLite local.

## Instalación

Requiere Python 3.12 y [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Uso

```bash
uv run uvicorn app.main:app --reload      # http://127.0.0.1:8000
uv run python scripts/seed.py             # carga un proyecto de ejemplo
uv run pytest                             # 125 tests
```

Flujo: creás un proyecto con su fecha de inicio, cargás tareas (indentándolas como
subtareas si querés), y vinculás las que dependen entre sí. Cada cambio recalcula todo
el cronograma y repinta el timeline sin recargar la página.

La **fecha de inicio del proyecto se edita en el resumen**, arriba de la grilla: si el
arranque se corre, todas las fechas se recalculan solas manteniendo las duraciones y las
dependencias.

Lo que ves en el timeline:

- **Barras azules** — tareas con holgura.
- **Barras rojas** — tareas que marcaste como críticas en la columna *Crít.*
  (criticidad de negocio: la decidís vos, no el cálculo). La holgura que sí calcula
  el motor está en el tooltip de cada barra.
- **Barras grises finas** — tareas resumen (las que tienen subtareas): su fecha es la
  envolvente de sus hijas, no se cargan a mano.
- **Rombos ◆** — hitos: marcan un momento, no ocupan días.
- **Flechas** — conectan cada tarea con las que dependen de ella. Salen y entran por
  el extremo que corresponde al tipo, así la relación se ve: Fin→Inicio va del final de
  una al arranque de la otra; Inicio→Inicio une los dos arranques y Fin→Fin los dos
  finales (esas dos, punteadas). Rojas si unen tareas sin margen.
- **Línea amarilla** — hoy, si cae dentro del rango del proyecto.
- **⚑** — la tarea tiene una restricción "no arrancar antes de".

El ancho de las columnas se achica solo en proyectos largos, para que un año entre en
la pantalla sin scrollear kilómetros.

## Reglas del motor (v1)

- Duración en **días hábiles** (lunes a viernes; sin feriados todavía).
- **Duración 0 = hito**: inicio y fin el mismo día, y no consume tiempo — lo que
  depende de un hito arranca el mismo día que el hito.
- Tres tipos de dependencia, entre tareas sin subtareas:
  **Fin→Inicio** (`1.3`, el normal), **Inicio→Inicio** (`1.3SS`, arrancan juntas) y
  **Fin→Fin** (`1.3FF`, terminan juntas). El lag va pegado: `1.3+2` espera dos días
  hábiles, `1.3SS-1` arranca uno antes.
- Una tarea arranca en el máximo entre el inicio del proyecto, su restricción SNET, y
  (fin de cada predecesora + 1 día hábil + lag). Nada arranca antes del inicio del
  proyecto, ni con lag negativo.
- Los ciclos se detectan y se rechazan al guardar, nombrando las tareas involucradas.

## Importar

Dos caminos, según lo que quieras:

- **Proyecto nuevo** — desde *Importar desde planilla*, en la home. Muestra una
  previsualización con los avisos y no crea nada hasta que confirmás.
- **Sumar a un proyecto abierto** — desde el botón *Importar planilla* dentro del
  proyecto. Las tareas se agregan al final con su jerarquía y sus dependencias. Si un
  código WBS ya estaba usado, la fila entra con uno libre y queda avisado.

**Desde una planilla `.xlsx`.** Hay una **plantilla modelo descargable** desde la misma
pantalla: trae el formato armado y las columnas de códigos ya en modo texto, para que
Excel no convierta un WBS como `4.6` en una fecha.

Necesita las columnas `WBS` y `Tarea`; si están, también lee `Predec.`, `Días`, `Resp.`,
`Crít.` y `_tipo` (fase / tarea / hito). El WBS arma la jerarquía (`2.3` cuelga de `2`) y
las predecesoras se escriben por WBS, separadas por coma, con lag opcional pegado al
código (`1.3+2` espera dos días hábiles, `1.3-1` solapa uno). Las fechas **no se cargan**:
las calcula la app.

Si el archivo tiene varias hojas, elegís cuál; por default toma la última que tenga las
columnas de tareas, salteando hojas de notas o ayuda.

Tres cosas del mundo real que el importador resuelve y **te reporta**:

- Excel suele convertir un WBS como `4.6` en la fecha `2026-06-04`. La conversión es
  reversible sin ambigüedad, así que se repara y queda anotado en los avisos.
- Una predecesora que apunta a un WBS que no está en la planilla no se crea, y te dice
  cuál era.
- **Fechas que contradicen a las dependencias.** Las columnas Inicio/Fin no se importan
  —el cronograma lo calcula el motor— pero sí se leen para detectar cuándo la planilla
  dice una cosa en Predec. y otra en las fechas. El caso típico: dos tareas declaradas
  en serie que figuran arrancando el mismo día, que en realidad son Inicio→Inicio. La
  previsualización te lo muestra y ofrece corregirlo.

**Pegando texto.** Una tarea por línea; la indentación (tabs o espacios) arma el árbol,
el número al final es la duración en días hábiles y `@alguien` el responsable. Una línea
que empieza con `Hito:` —o con duración 0— entra como hito.

```
Relevamiento
    Entrevistas con el cliente   4
    Informe de brechas   2  @Ariel
Hito: relevamiento cerrado
```

## Export

Desde la vista de un proyecto, arriba a la derecha:

- **`.json`** — dump completo: estructura, duraciones, dependencias con su lag y las
  fechas calculadas. Es el formato para backup portable o para alimentar otra
  herramienta.
- **`.md`** — el árbol indentado con fechas, marcando la ruta crítica y las tareas
  hechas. Para pegar en un informe o versionar en git y ver cómo se movió el
  cronograma entre semanas.

## Backup

Toda la información está en un único archivo SQLite (`wopr-proyectos.db` por default,
configurable con `WOPR_DB`). Copiarlo es el backup completo:

```bash
cp wopr-proyectos.db ~/backups/wopr-proyectos-$(date +%F).db
```

La DB no se commitea (está en `.gitignore`).

## Configuración

Todo por variables de entorno, con defaults pensados para uso local:

| Variable | Default | Qué hace |
|---|---|---|
| `WOPR_HOST` | `127.0.0.1` | Interfaz de escucha. **Exponerlo fuera de localhost exige auth + HTTPS antes.** |
| `WOPR_PORT` | `8000` | Puerto |
| `WOPR_DB` | `./wopr-proyectos.db` | Ruta del archivo SQLite |
| `WOPR_DEBUG` | `false` | Modo debug; apagado por default |

## Arquitectura

```
routers → services → engine | models/db
```

`app/engine/` es el corazón: Python puro, sin FastAPI ni SQLModel. Entra y sale por las
dataclasses de `engine/types.py`, y se testea sin DB ni servidor. El resto de la app le
traduce los modelos y pinta el resultado.

Detalle de fases, reglas y criterios en `PLAN-DE-OBRA.md`; convenciones en `CLAUDE.md`.

## Terceros

`static/htmx.min.js` es [htmx](https://htmx.org/) 2.0.7 (licencia MIT), vendoreado para
no depender de ninguna CDN.
