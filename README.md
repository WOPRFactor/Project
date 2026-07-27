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
uv run pytest                             # 67 tests
```

Flujo: creás un proyecto con su fecha de inicio, cargás tareas (indentándolas como
subtareas si querés), y vinculás las que dependen entre sí. Cada cambio recalcula todo
el cronograma y repinta el timeline sin recargar la página.

Lo que ves en el timeline:

- **Barras azules** — tareas con holgura.
- **Barras rojas** — ruta crítica: atrasar cualquiera de ellas atrasa el proyecto entero.
- **Barras grises finas** — tareas resumen (las que tienen subtareas): su fecha es la
  envolvente de sus hijas, no se cargan a mano.
- **Línea amarilla** — hoy, si cae dentro del rango del proyecto.
- **⚑** — la tarea tiene una restricción "no arrancar antes de".

## Reglas del motor (v1)

- Duración en **días hábiles** (lunes a viernes; sin feriados todavía).
- Dependencias **solo Fin→Inicio**, con lag en días hábiles: positivo espera, negativo
  solapa. Solo entre tareas sin subtareas.
- Una tarea arranca en el máximo entre el inicio del proyecto, su restricción SNET, y
  (fin de cada predecesora + 1 día hábil + lag). Nada arranca antes del inicio del
  proyecto, ni con lag negativo.
- Los ciclos se detectan y se rechazan al guardar, nombrando las tareas involucradas.

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
