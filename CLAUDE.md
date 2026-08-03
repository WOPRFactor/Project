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
uv run python -m app                   # levantar en http://127.0.0.1:1983 (WOPR_PORT lo cambia)
uv run pytest                          # correr tests
```

## Arquitectura

Dirección de dependencias única: `routers → services → engine | models/db`.

- `app/engine/` — **el corazón**: motor de scheduling en Python puro. No importa FastAPI
  ni SQLModel; entra y sale por las dataclasses de `engine/types.py`. Se testea sin DB y
  sin server, y es el módulo con mayor densidad de tests del repo.
- `app/auth/` — identidad y permisos, sin lógica de negocio: hash, sesiones, CSRF y
  las dependencias que los routers usan para exigir cuenta.
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
- **Ámbito** por tarea (proyecto / seguimiento / control): afecta el *reporte*, nunca
  el cálculo. Separa el alcance comprometido del acompañamiento posterior.
- **Peso** por tarea: se declara como **% del padre**, nunca del proyecto. Así cada
  nivel cierra por su cuenta y agregar una tarea no rompe la suma del árbol entero.
  El peso absoluto es derivado (se multiplica desde la raíz) y no se guarda. `None` =
  "repartir en partes iguales lo que sobre". Que un nivel no dé 100 **se avisa, no se
  bloquea**: frenar la carga a mitad de camino sería infumable. El avance del proyecto
  es **ponderado** — Σ (peso absoluto × avance de la tarea) —, porque contar cabezas
  hace pesar lo mismo una firma de acta de un día que 120 días de acompañamiento.
- **Responsable = persona del proyecto**, no texto por tarea. La celda sigue siendo
  texto libre con autocompletado y el service la resuelve contra los contactos
  existentes, uniendo por nombre normalizado (sin acentos ni mayúsculas). Obligar a
  dar de alta a alguien antes de escribirlo se abandona a la tercera fila.
- **Estados definibles por proyecto.** El nombre y el color los elige el usuario; lo
  único que el motor necesita saber de un estado es `es_final`. Nunca comparar contra
  el string "hecha". `avance_sugerido` es lo que la tarea aporta al avance ponderado
  mientras no exista avance real por tarea.
- **Duración optimista / probable / pesimista**: el motor calcula los tres escenarios
  (`Escenario`) y la app muestra la ventana de fin. Sin rango declarado, los tres
  coinciden.
- Recálculo total del cronograma en cada cambio — no optimizar lo que no duele.

## Convenciones

- **Tamaño:** objetivo ≤ 200 líneas por archivo, techo 300. Función ≤ ~40-50 líneas.
  Excepción justificada se documenta en una línea al tope. Se modulariza por
  *responsabilidad*, no por conteo.
- Un archivo, una responsabilidad. Capacidad nueva = archivo nuevo que respeta el
  contrato, no crecimiento del existente.
- Todo cambio de lógica llega con su test; los del engine no tocan la DB; los de
  services no levantan el server. Los de `tests/navegador/` son opcionales: corren
  solo con Playwright instalado (`uv sync --group navegador`) sobre el Chrome del
  sistema; sin él, pytest saltea la carpeta.
- UI en castellano.

## Seguridad

- La app bindea **solo `127.0.0.1`**. Si alguna vez se expone fuera de localhost,
  auth + HTTPS son requisito previo, no deuda técnica.
- **Ninguna consulta parte de un id crudo** (Fase 11). Toda ruta de proyecto pasa por
  `exige_lector/editor/duenio`, que resuelven entidad **y** permiso juntos y devuelven
  un `Acceso`; al no-miembro le responden **404 y no 403** (un 403 confirmaría que el
  proyecto existe). Tres roles por proyecto y nada más: dueño / editor / lector.
  Esconder el botón en la UI **no** es un control — el endpoint rechaza igual.
- **Desde la Fase 10 la app tiene puerta** (`app/auth/`): contraseñas con argon2id
  (el hash no sale nunca de `auth/hash.py`), sesiones como fila revocable con token
  opaco en cookie `HttpOnly`, y **token CSRF exigido por middleware en todo verbo
  que no sea GET** — una ruta nueva nace protegida sin que nadie se acuerde. Las
  cuentas las crea el admin: no hay auto-registro. `WOPR_SECRET_KEY` es obligatoria
  fuera de modo debug.
- **Nadie pisa el trabajo de otro en silencio** (Fase 12). La base va en **WAL** con
  espera por lock, y cada `Task` tiene `version`: la celda manda la que leyó y una
  vencida se rechaza con **409** más la fila recargada. La versión la sube un listener
  de `before_flush` en `app/concurrencia.py`, **no cada service a mano** — una tarea se
  guarda desde el árbol, las predecesoras, los pesos y el import, y el que se olvidara
  abriría justo el agujero que esto tapa. HTMX no pinta respuestas que no sean 2xx: el
  swap del 409 se habilita explícitamente en `static/grilla.js`.
- La tabla `cambio` es **de solo agregar**: la escriben los services (foto antes / foto
  después) y ninguna ruta la edita ni la borra. Guarda texto ya legible y no ids —un id
  de estado borrado no se puede resolver tres meses después—, y sobrevive al borrado de
  la tarea, que es justo cuando más importa.
- El esquema lo versiona **Alembic** (`migrations/`), no un script aditivo.
- **Los documentos (PDF y Word) no rearman nada** (Fase 30). El PDF lo imprime el Chrome
  del sistema sobre la **misma plantilla** que la pantalla, porque el Gantt ya es HTML y
  CSS: redibujarlo en otra librería sería garantizar que papel y pantalla se separen. Por
  eso el informe vive en `informe/cuerpo.html`, incluido por la pantalla y por el PDF. El
  HTML del documento va **autocontenido** (CSS embebido con `css_embebido`): se imprime
  desde un `file://` donde `/static/...` no resuelve. Word es la excepción declarada: va
  sin Gantt, porque ahí sí habría que redibujarlo.
- Un documento **no depende de la mirada**: sale con todas las tareas, aunque en pantalla
  tengas etapas plegadas y columnas apagadas. Y el Gantt se **comprime** al ancho de la
  hoja (`documento.ancho_de_dia`, truncando centésimos hacia abajo): Chrome corta lo que
  se pasa del ancho **sin avisar**, y perder los últimos meses del cronograma es peor que
  un Gantt apretado.
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

- Columnas editables: WBS, Tarea, Resp., Predec., Días, Opt·Pes, Inicio, **Crít.**,
  **Peso**, **Avance**, **Riesgo**, **Estado**, Ámbito. Calculadas (nunca editables): Fin y el % del proyecto
  que se muestra al lado del peso, y el **Desvío** contra la línea base vigente.
- **Criticidad ≠ ruta crítica.** `Task.critica` es criticidad *de negocio*: la marca
  el usuario por KPI o impacto, y es la que pinta la barra en rojo. La ruta crítica
  del motor (holgura cero) es otra cosa y se expone como `Fila.sin_holgura` y como
  la holgura en días. Nunca se pisan entre sí.
- La **mirada** (detalle, etapa, color, columnas, etapas plegadas ▾/▸ y flechas del
  timeline) viaja en la URL y **persiste por proyecto** (`Project.vista`): salir y
  volver la retoma; un link con parámetros la pisa. Plegar etapas es orden visual,
  nunca filtra los totales.
- El árbol se lee **por color**: etapas en azul de acento (negrita, fondo azulado),
  críticas en el mismo rojo que su barra (título, WBS y filo izquierdo), terminadas
  en gris tachado.
- Arriba de la grilla, el **resumen** muestra inicio, fin, próximo hito y avance; abajo,
  un bloque por ámbito con su **ventana** (calendario, se superponen entre sí) y su
  **esfuerzo** (suma de duraciones, es trabajo). Dos unidades distintas, nunca juntas.
  La holgura se mide contra el fin del **ámbito** de cada tarea, no contra el fin
  global: si no, el acompañamiento posterior le regala meses de margen al resto. Vive dentro del tablero para recalcularse en
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
