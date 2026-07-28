# WOPR Proyectos

Planificador de proyectos personal de Ariel, estilo MS Project pero local y propio:
tareas con subtareas, dependencias Fin→Inicio, y un timeline semanal (Gantt) con fechas
**calculadas** por un motor de scheduling. App web **local** (un usuario, sin auth).
El plan de obra completo, con fases, reglas del motor y criterios de hecho, está en
`PLAN-DE-OBRA.md` — leelo antes de implementar cualquier fase.

## Stack

Python 3.12 · FastAPI · SQLModel sobre SQLite · Jinja2 + HTMX (vendoreado en `static/`,
sin CDN) · timeline pintado server-side con CSS Grid · openpyxl para importar planillas ·
entorno y dependencias con `uv`.

## Comandos

```bash
uv sync                                # instalar dependencias
uv run uvicorn app.main:app --reload   # levantar en http://127.0.0.1:8000
uv run pytest                          # correr tests
```

## Arquitectura

Dirección de dependencias única: `routers → services → engine | models/db`.

- `app/engine/` — **el corazón**: motor de scheduling en Python puro. No importa FastAPI
  ni SQLModel; entra y sale por las dataclasses de `engine/types.py`. Se testea sin DB y
  sin server, y es el módulo con mayor densidad de tests del repo.
- `app/routers/` — HTTP puro: parsear request, llamar al service, renderizar. Sin lógica.
- `app/services/` — lógica de negocio; `services/schedule.py` puentea models → engine.
  No importan FastAPI ni templates.
- `app/models.py` — `Project`, `Task` (árbol vía `parent_id`), `Dependency`, enums.
- `app/migraciones.py` — agrega al arranque las columnas nuevas a una base ya
  existente. Campo nuevo en un modelo = anda solo; renombrar o borrar necesita más.
- `app/templates/` — Jinja2 con parciales para HTMX; el Gantt es HTML/CSS generado, y
  las flechas entre barras un SVG superpuesto cuya geometría calcula `engine/timeline.py`
  (es geometría pura, se testea sin navegador).

## Reglas del motor (v1 — no ampliar sin tocar el plan)

- Tarea con hijas = *resumen*: sin duración propia, fechas por rollup (envolvente).
- Duración 0 = **hito**: inicio y fin el mismo día, y no consume tiempo — lo que
  depende de un hito arranca el mismo día que el hito (`scheduler.salto_tras`).
- Dependencias **FS / SS / FF con lag** (días hábiles, negativo = adelanta), solo entre
  tareas hoja. SS existe porque el trabajo que corre *en paralelo* a otro (supervisar
  mientras se ejecuta) declarado como FS empuja el cronograma. Ciclos: detectados y
  rechazados al guardar, con error claro — jamás un 500 ni un loop.
- **El import no confía en las fechas de la planilla, pero tampoco las tira.** Las usa
  para detectar dependencias mal declaradas (`services/importar_diagnostico.py`): compara
  *relaciones*, no fechas absolutas, así un corrimiento global no genera ruido.
- Duración en **días hábiles** (L-V, sin feriados en v1). Restricción opcional por
  tarea: "no arrancar antes de X" (SNET).
- Recálculo total del cronograma en cada cambio — no optimizar lo que no duele.

## Convenciones

- **Tamaño:** objetivo ≤ 200 líneas por archivo, techo 300. Función ≤ ~40-50 líneas.
  Excepción justificada se documenta en una línea al tope. Se modulariza por
  *responsabilidad*, no por conteo.
- Un archivo, una responsabilidad. Capacidad nueva = archivo nuevo que respeta el
  contrato, no crecimiento del existente.
- Todo cambio de lógica llega con su test; los del engine no tocan la DB; los de
  services no levantan el server.
- UI en castellano.

## Seguridad

- La app bindea **solo `127.0.0.1`**. Si alguna vez se expone fuera de localhost,
  auth + HTTPS son requisito previo, no deuda técnica.
- Todo input externo se valida con Pydantic en el borde: tipos, longitudes, enums
  cerrados, duración entera > 0, fechas parseadas estricto.
- El grafo de dependencias también es input: se valida (ciclos, referencias colgantes,
  dependencias a resúmenes) antes de calcular.
- Acceso a datos solo por ORM (SQLModel). SQL concatenado a mano: nunca.
- Jinja2 con autoescape activo; prohibido `|safe` sobre contenido de usuario.
- Sin secretos en el repo ni en el código; si aparece uno, va por variable de entorno.
- Debug apagado por default; los errores al navegador no muestran stack traces.
- La DB SQLite (`*.db`) no se commitea.

## La grilla (Fase 7)

La grilla **es** la aplicación, como en MS Project o Smartsheet: cada celda se edita
en el lugar y cada cambio recalcula el cronograma entero. No hay formularios aparte.

- Columnas editables: WBS, Tarea, Resp., Predec., Días, Inicio, **Crít.**
  Calculada (nunca editable): Fin.
- **Criticidad ≠ ruta crítica.** `Task.critica` es criticidad *de negocio*: la marca
  el usuario por KPI o impacto, y es la que pinta la barra en rojo. La ruta crítica
  del motor (holgura cero) es otra cosa y se expone como `Fila.sin_holgura` y como
  la holgura en días. Nunca se pisan entre sí.
- Arriba de la grilla, el **resumen** muestra inicio, fin, duración total en días
  hábiles, tareas, hitos y avance. Vive dentro del tablero para recalcularse en
  cada cambio. La **fecha de inicio del proyecto se edita ahí mismo**: moverla
  recalcula todas las fechas conservando duraciones y dependencias.
- **Inicio** solo es editable si la tarea no tiene predecesoras; si las tiene, la fecha
  la manda la dependencia y se muestra en gris.
- Las **predecesoras se escriben por código WBS**: `1.3`, `1.3+2` (espera 2 días
  hábiles), `1.3-1` (solapa 1). Varias, separadas por coma. La celda es la fuente de
  verdad: lo que no está escrito, se borra.
- El **código WBS** se genera al crear la fila y después queda estable — renumerar es
  una acción explícita, porque reescribirlo rompería las referencias escritas a mano.
  Es único en todo el proyecto, no solo entre hermanas.
