# Plan de obra — WOPR Proyectos

Planificador de proyectos personal de Ariel, estilo MS Project / Smartsheet pero local y
propio: tareas con **subtareas**, **dependencias** entre tareas, y un **timeline que pinta
las semanas calculadas** a partir de duraciones y dependencias. App web local, uso
personal e iterativo.

El corazón de la herramienta no es el CRUD — es el **motor de cálculo de cronograma**:
un grafo de dependencias que se ordena, se recorre y produce fechas. Ese motor es Python
puro, sin conocer web ni base de datos, y es lo que más tests se lleva.

## Resumen

| | |
|---|---|
| Qué es | Planificador con árbol de tareas, dependencias y timeline semanal calculado (Gantt) |
| Para quién | Ariel, uso personal |
| Dónde corre | Local, navegador contra `127.0.0.1` — sin exposición de red |
| Datos | Propios, sin secretos ni datos de terceros en v1 |
| Producción | No — herramienta personal iterativa |

## Supuestos

Reglas de negocio del motor v1. Son las decisiones que en MS Project son configurables;
acá arrancan fijas y simples. Corregí lo que no cierre antes de la Fase 3.

1. **Jerarquía:** las tareas forman árbol de profundidad libre. Una tarea con hijas es
   *resumen*: no tiene duración propia — sus fechas son la envolvente de sus hijas
   (rollup, como en MS Project).
1b. **Hito = duración 0** (agregado en Fase 6): marca un momento, inicio y fin el mismo
   día, y no consume tiempo — su sucesora arranca el mismo día que el hito.
2. **Dependencias solo Fin→Inicio (FS), con lag**, y solo entre tareas hoja. El lag se
   expresa en días hábiles y puede ser negativo (solape): "arranca 3 días después de que
   termine X" o "puede empezar 2 días antes de que X termine". Otros tipos (SS, FF)
   quedan para v2. Ciclos: prohibidos y detectados al guardar.
3. **Duración en días hábiles** (lunes a viernes). Feriados configurables: v2.
4. **Cálculo:** el proyecto tiene fecha de inicio; una tarea arranca en el máximo
   (fin de predecesora + 1 día hábil + lag) sobre todas sus predecesoras, o al inicio del
   proyecto si no tiene. Restricción opcional por tarea: "no arrancar antes de X" (SNET).
   Nada arranca antes del inicio del proyecto, ni siquiera con lag negativo. Sin recursos
   ni nivelación — no hay equipo.
5. **Recálculo total en cada cambio.** Con proyectos personales (cientos de tareas, no
   decenas de miles) el recálculo completo es instantáneo; no se optimiza lo que no duele.
6. **Un solo usuario, sin login**, solo `127.0.0.1`. Si algún día se expone fuera,
   auth + HTTPS son requisito previo, no deuda.
7. **SQLite local**, la DB no va a git. UI en castellano.

## Arquitectura y stack

> **Decisión a validar** — recomendación con alternativa; confirmá antes de la Fase 1.

**Recomendado: Python 3.12 + FastAPI + Jinja2 + HTMX + SQLite (SQLModel).** Se sostiene
del plan anterior y ahora con más razón: el motor de scheduling es Python puro
(`datetime` + un toposort, sin dependencias exóticas) y el resto es servir vistas. Un
proceso, cero build step, cero npm.

**El timeline se pinta server-side con CSS Grid:** columnas = semanas (ISO), cada tarea
una barra que ocupa `grid-column: semana_inicio / semana_fin`. Sin librería JS de Gantt:
es HTML que Jinja arma desde el cronograma calculado, y HTMX lo re-renderiza tras cada
cambio. Para un Gantt de *lectura* con edición por formularios, alcanza y sobra.

**Alternativa razonable:** vendorear **frappe-gantt** (JS liviano, MIT) si querés barras
arrastrables para mover fechas con el mouse. Costo: un puente JS↔API y estado en el
cliente. Mi consejo: CSS Grid en v1, frappe-gantt como upgrade de v2 si la edición por
formulario te queda corta — el motor no cambia en nada.

**Descartado:** SPA (React/Svelte) — dos toolchains para un usuario; MS Project/Smartsheet
— el punto es datos propios en SQLite integrables al ecosistema WOPR.

**Gestión de entorno:** `uv`, dependencias pinneadas.

### Superficie de ataque

- **Entra de afuera:** solo el navegador local. Todo input validado con Pydantic en el
  borde: tipos, longitudes, enums, duraciones > 0, fechas parseadas estricto.
- **El grafo también es input:** el motor valida ciclos y referencias colgantes antes de
  calcular — un grafo inválido devuelve error claro, nunca un loop infinito ni un 500.
- **Red:** bind solo `127.0.0.1`. **ORM** parametrizado, sin SQL a mano. **Jinja** con
  autoescape, sin `|safe` sobre datos de usuario. **Secretos:** v1 no tiene; si aparecen,
  por env. **Errores:** debug apagado, sin stack traces al navegador.

## Estructura del repo

Modular desde el arranque: una responsabilidad por archivo, objetivo ≤ 200 líneas
(techo 300, excepción documentada). El motor no importa nada de FastAPI ni de SQLModel:
recibe dataclasses planas y devuelve un cronograma — se testea sin DB y sin server.

```
wopr-proyectos/
├── CLAUDE.md
├── PLAN-DE-OBRA.md
├── README.md
├── pyproject.toml
├── .gitignore
├── app/
│   ├── main.py               # wiring: crea la app, monta routers
│   ├── config.py             # settings desde env con defaults
│   ├── db.py                 # engine SQLite, sesión, init
│   ├── models.py             # Project, Task (parent_id), Dependency + enums
│   ├── engine/               # ★ motor de scheduling — Python puro
│   │   ├── types.py          # dataclasses: TaskNode, Schedule, errores del motor
│   │   ├── calendar.py       # días hábiles: sumar, contar, siguiente hábil
│   │   ├── graph.py          # toposort, detección de ciclos, validación del grafo
│   │   └── scheduler.py      # forward pass (fechas), rollup de resúmenes, semanas
│   ├── routers/
│   │   ├── projects.py
│   │   ├── tasks.py          # CRUD de tareas/subtareas y dependencias
│   │   └── timeline.py       # vista Gantt semanal
│   ├── services/
│   │   ├── projects.py
│   │   ├── tasks.py          # árbol, validación de negocio, llama al engine
│   │   └── schedule.py       # puente models → engine → cronograma para vistas
│   └── templates/            # Jinja2 + parciales HTMX (timeline como CSS Grid)
├── static/                   # CSS del Gantt, htmx.min.js vendoreado
└── tests/
    ├── engine/               # la mayor densidad de tests vive acá
    │   ├── test_calendar.py
    │   ├── test_graph.py
    │   └── test_scheduler.py
    ├── test_projects.py
    └── test_tasks.py
```

Dirección de dependencias única: `routers → services → engine | models/db`. El engine no
depende de nadie.

## Fases

Ninguna fase se cierra si un archivo supera 300 líneas o si su control de seguridad quedó
afuera.

### Fase 1 — Esqueleto que arranca
Repo con `uv`, FastAPI + SQLModel + Jinja montados, modelos `Project`, `Task` (con
`parent_id`, duración, SNET opcional) y `Dependency`, config por env, home vacía,
healthcheck. Paquete `app/engine/` creado con sus tipos base y tests placeholder.
**Hecho cuando:** `uv run uvicorn app.main:app` levanta solo en `127.0.0.1:8000`, la DB
se crea sola, deps pinneadas, y pytest corre verde.

### Fase 2 — Proyectos y árbol de tareas
CRUD de proyectos (nombre, fecha de inicio, estado) y de tareas con **subtareas**: crear
bajo un padre, editar, mover de padre, borrar con confirmación (borrar padre pregunta qué
hacer con las hijas). Vista de árbol indentado con expandir/colapsar vía HTMX. Sin fechas
calculadas todavía — duración y orden se cargan, no se pintan.
**Hecho cuando:** un árbol de 3+ niveles vive su ciclo completo desde el navegador, mover
una tarea de padre no rompe el árbol (validado: no podés colgar una tarea de su propia
descendiente), services testeados aislados.

### Fase 3 — El motor: dependencias y cálculo ★
La fase más importante. CRUD de dependencias FS entre tareas hoja (con rechazo de ciclos
y de dependencias a resúmenes, error claro al usuario). En `app/engine/`: calendario
hábil, toposort con detección de ciclos, forward pass que asigna inicio/fin a cada hoja
(max fin de predecesoras, respetando SNET), rollup de resúmenes, y fin de proyecto.
**Hecho cuando:** el engine pasa una batería de tests con casos armados a mano: cadena
simple, diamante, ciclo detectado, SNET que empuja, rollup multinivel, fin de semana
salteado, tarea sin predecesoras. Cada cambio de tarea/dependencia dispara recálculo y
las fechas quedan visibles en el árbol. Grafo inválido nunca tira 500.

### Fase 4 — Timeline: pintar las semanas
La vista Gantt. Cabecera de semanas ISO (con mes), una fila por tarea siguiendo el árbol
(resúmenes como barras envolventes), cada barra ocupando sus semanas calculadas via CSS
Grid. Línea de "hoy". Al editar duración o dependencia desde el panel, HTMX re-renderiza
el timeline ya recalculado. **Ruta crítica** resaltada (backward pass en el engine: holgura
cero = crítica).
**Hecho cuando:** un proyecto real tuyo se carga y el timeline se lee de un vistazo, las
barras coinciden con las fechas del motor (test de la transformación cronograma→grid), la
ruta crítica se distingue, y todo re-pinta tras cada cambio sin recargar la página.

### Fase 5 — Cierre v1: estado, export y pasada de seguridad
Estado de avance por tarea (pendiente/en curso/hecha) visible en árbol y timeline. Export
a JSON (dump completo) y Markdown (un `.md` por proyecto con árbol y fechas). Seed con un
proyecto de ejemplo con dependencias. README. Pasada final de seguridad.
**Hecho cuando:** export válido y legible, app levantable en máquina limpia solo con el
README, y pasada limpia: input validado en bordes, cero secretos en repo, deps sin CVEs
conocidos, sin stack traces al navegador, bind solo-localhost re-verificado. Correr
`/security-review` sobre el diff antes de cerrar.

### Fase 6 — Importar: planilla y texto pegado ✔
Nace de una planilla real de Ariel (Gantt de traspaso operativo), que destapó dos
huecos del modelo: **hitos** (duración 0) y **responsable**. Import desde `.xlsx`
leyendo WBS, Tarea, Resp., Predec., Días y `_tipo`, con previsualización obligatoria
antes de crear nada; y pegado de texto indentado para la carga rápida. Suma
`app/migraciones.py`, porque agregar columnas rompe una base ya existente.
**Hecho cuando:** la planilla real entra completa (41 filas, 38 dependencias) con sus
avisos, el cronograma calcula sin errores, y una base de la versión anterior sigue
abriendo. ✔ Verificado en navegador; 125 tests.

## Prompts para Code

Uno por fase, en orden; cada uno asume el anterior terminado.

### Prompt Fase 1
> Leé CLAUDE.md y PLAN-DE-OBRA.md. Implementá la Fase 1 de WOPR Proyectos: proyecto
> Python 3.12 con uv; FastAPI + SQLModel + Jinja2; estructura exacta del plan incluyendo
> el paquete app/engine/ con types.py (dataclasses TaskNode, Schedule y errores del
> motor) y módulos vacíos con firma. Modelos Project (nombre, fecha_inicio, estado),
> Task (project_id, parent_id nullable, título, duración en días hábiles, snet nullable,
> estado, orden) y Dependency (predecessor_id, successor_id, unique). Config por env con
> defaults (host 127.0.0.1, puerto 8000, ruta DB). DB autoinicializada. Home Jinja vacía
> y healthcheck. htmx.min.js vendoreado, sin CDN.
> Criterios de aceptación: levanta con `uv run uvicorn app.main:app` y SOLO bindea
> 127.0.0.1; deps pinneadas; autoescape activo; debug off por default; pytest verde con
> tests mínimos de healthcheck y creación de Project; ningún archivo > 300 líneas.

### Prompt Fase 2
> Implementá la Fase 2: CRUD de proyectos y árbol de tareas con subtareas según el plan.
> Routers delgados, lógica en services puros (sin imports de FastAPI). Vista de árbol
> indentado con expandir/colapsar y alta/edición por parciales HTMX. Mover tarea de
> padre validando que no se cuelgue de su propia descendencia. Borrado con confirmación;
> borrar un padre ofrece borrar o re-colgar las hijas. Validación Pydantic en el borde:
> título requerido con máximo, duración entera > 0, fechas estrictas, enums cerrados.
> Criterios de aceptación: árbol de 3+ niveles con ciclo de vida completo desde el
> navegador; input inválido da error claro sin stack trace; tests de service para crear/
> mover/borrar incluyendo el caso descendencia-inválida; límites de tamaño respetados.

### Prompt Fase 3
> Implementá la Fase 3, el motor de scheduling. En app/engine/ (Python puro, sin imports
> de FastAPI ni SQLModel, entra y sale por las dataclasses de types.py):
> calendar.py (sumar/contar días hábiles L-V, siguiente hábil), graph.py (toposort,
> detección de ciclos con reporte de cuáles nodos, validación de referencias), y
> scheduler.py (forward pass: inicio = max fin de predecesoras o inicio de proyecto,
> respetando SNET; fin = inicio + duración en hábiles; rollup de resúmenes como
> envolvente; fechas del proyecto). CRUD de dependencias FS solo entre hojas, rechazando
> ciclos y dependencias a resúmenes con error claro al usuario. services/schedule.py
> puentea models → engine y cada cambio recalcula; las fechas aparecen en el árbol.
> Criterios de aceptación: tests del engine para cadena, diamante, ciclo detectado, SNET
> que empuja, rollup multinivel, salto de fin de semana y tarea suelta; un grafo inválido
> jamás produce 500 ni loop; el engine no toca DB en ningún test; límites de tamaño
> respetados (si scheduler.py crece, partí backward pass a su propio módulo).

### Prompt Fase 4
> Implementá la Fase 4: el timeline semanal. Vista Gantt server-rendered con CSS Grid:
> cabecera de semanas ISO con mes, filas siguiendo el orden e indentación del árbol,
> barras posicionadas por grid-column desde las semanas calculadas, resúmenes con estilo
> propio, línea vertical de "hoy". Agregá al engine el backward pass y holgura; holgura
> cero = ruta crítica, resaltada en el timeline. Editar duración/dependencias desde un
> panel re-renderiza el timeline recalculado vía HTMX, sin recargar.
> Criterios de aceptación: test de la transformación cronograma→columnas de grid
> (incluye tareas que cruzan de año ISO); tests de backward pass y ruta crítica en el
> engine; timeline legible con un proyecto de 30+ tareas; sin JS más allá de HTMX;
> límites de tamaño respetados.

### Prompt Fase 5
> Implementá la Fase 5 y cerrá la v1: estado de avance por tarea visible en árbol y
> timeline (con estilo distinto para hechas); export a JSON completo y a Markdown por
> proyecto (árbol indentado con fechas calculadas); seed de ejemplo con dependencias;
> README con instalación, uso y backup. Pasada final de seguridad: input validado en
> todos los bordes, cero secretos en repo, deps pinneadas sin CVEs conocidos, errores
> sin stack trace, bind solo-localhost verificado, autoescape sin |safe sobre datos de
> usuario. Corré /security-review sobre el diff y resolvé lo que salga.
> Criterios de aceptación: export válido y legible; app levantable en máquina limpia
> siguiendo solo el README; pasada de seguridad limpia y review corrido.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| **El motor es el proyecto.** Si el cálculo da fechas raras, la herramienta no sirve, por linda que sea la UI. | Fase 3 dedicada, engine puro con la mayor densidad de tests del repo, casos de borde enumerados en el criterio de hecho. La UI llega recién en Fase 4, sobre un motor ya confiable. |
| **Scope creep hacia MS Project completo** (recursos, lag, SS/FF, feriados, baselines). | Reglas v1 cerradas en Supuestos. Cada agregado es una fase nueva contra este plan; el diseño del engine (tipos propios, un solo tipo de dependencia hoy) deja espacio sin pagarlo por adelantado. |
| **Seguridad:** riesgo bajo — sin red expuesta, sin secretos, un usuario. El riesgo real es exponerla en LAN "un rato" sin auth. | Regla dura declarada acá y en CLAUDE.md: fuera de `127.0.0.1` ⇒ auth + HTTPS previos, no deuda. Además el grafo se trata como input hostil (ciclos, referencias) aunque venga de vos. |
| Pérdida de datos (SQLite local). | Export de Fase 5 + backup documentado en README; la DB no va a git. |
| El Gantt CSS Grid queda corto si querés arrastrar barras. | Decisión consciente de v1; el upgrade (frappe-gantt vendoreado) no toca el motor. Está en Arquitectura como alternativa. |
