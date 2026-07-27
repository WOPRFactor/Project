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
- `app/templates/` — Jinja2 con parciales para HTMX; el Gantt es HTML/CSS generado.

## Reglas del motor (v1 — no ampliar sin tocar el plan)

- Tarea con hijas = *resumen*: sin duración propia, fechas por rollup (envolvente).
- Duración 0 = **hito**: inicio y fin el mismo día, y no consume tiempo — lo que
  depende de un hito arranca el mismo día que el hito (`scheduler.salto_tras`).
- Dependencias solo **Fin→Inicio con lag** (en días hábiles, puede ser negativo = solape)
  y solo entre tareas hoja. Ciclos: detectados y rechazados al guardar, con error claro
  — jamás un 500 ni un loop.
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
