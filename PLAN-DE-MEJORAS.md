# Plan de mejoras — WOPR Proyectos v2

Continúa `PLAN-DE-OBRA.md`, que cubre las fases 1 a 9 (v1: motor de scheduling, grilla
editable, Gantt con flechas, ámbitos, import de planilla). Este documento cubre v2, que son
**tres cosas distintas** y conviene no mezclarlas:

- **Multiusuario** es un cambio de *postura*. Hoy la app confía en todo lo que le llega
  porque del otro lado hay una sola persona en su propia máquina. Con dos usuarios eso se
  termina: cada consulta pasa a necesitar un dueño, cada escritura un permiso, y el proceso
  deja de estar solo detrás de `127.0.0.1`. Es la parte con una **puerta de seguridad dura**:
  no se expone nada hasta que auth y HTTPS estén cerrados.
- **El modelo de trabajo** es lo que hoy le falta al proyecto para que un informe diga algo:
  pesos, estados propios, responsables de verdad, línea base y avance real. Sin esto, un
  informe es la grilla impresa.
- **Los informes** son la salida: cuadrante de riesgos, Gantt por etapas, Excel, PDF.

El orden entre los tres no es estético. **Multiusuario primero** porque es la única puerta
de seguridad; **el modelo después** porque el informe consume lo que el modelo produce; **el
informe al final** porque es lo único que no habilita nada más.

## Resumen

| | |
|---|---|
| Qué suma | Usuarios con permisos, trabajo simultáneo, pesos, estados propios, responsables, riesgos con cuadrante, comentarios, adjuntos, Gantt por etapas, Excel e informe imprimible |
| Para quién | Ariel (dueño), su equipo (carga), clientes y dirección (lectura del informe) |
| Dónde corre | Servidor propio o VPS. **El proceso sigue bindeando `127.0.0.1`**; el TLS lo termina un proxy adelante |
| Datos | Deja de ser solo de Ariel: hay datos de terceros, credenciales y **archivos subidos**. Cambia la clasificación del proyecto |
| Producción | **Sí.** A partir de la Fase 13 esto es un servicio, no un experimento |

Ese último renglón es el que manda: todo lo que en v1 se justificaba con "es local y lo uso
yo" deja de tener validez.

## Supuestos

Corregí lo que no cierre **antes de la Fase 10** — varios cambian el modelo de datos.

1. **Los usuarios los da de alta el dueño. No hay auto-registro.** Es la simplificación más
   rentable del plan: elimina el registro público, la verificación por mail, el "olvidé mi
   contraseña" con SMTP y el abuso de altas. Ariel crea el usuario y entrega una contraseña
   de un solo uso que se cambia al primer login.
2. **Tres roles por proyecto: dueño / editor / lector.** El dueño administra miembros, pesos
   y línea base; el editor carga y edita; el lector solo ve. Nada de permisos por tarea ni
   por columna.
3. **Un `admin` global** (Ariel) que crea usuarios y ve todo.
4. **Decenas de usuarios, no miles.** Define todas las decisiones de infraestructura.
5. **Sin colaboración en vivo.** Dos personas trabajan sobre el mismo proyecto, pero no se
   sincronizan en tiempo real. Lo que sí se garantiza es que **nadie pisa el trabajo de otro
   en silencio** (Fase 12).
6. **El avance lo carga una persona.** Sin integración con Jira ni con el repo.
7. **El peso es de negocio, no de duración.** Lo define el usuario porque el valor de una
   etapa no es proporcional a lo que tarda. La app ofrece repartirlo por duración o en
   partes iguales como punto de partida, pero la última palabra es humana.
8. **Los pesos se expresan como % del padre**, no como % del proyecto. Ver *Decisiones*.
9. **La línea base la congela el dueño explícitamente**, y puede haber varias. Una sola está
   *vigente* y es contra la que se mide el desvío.
10. **El informe es un documento a fecha de corte**, no un dashboard vivo.
11. **Sin notificaciones por mail** en v2. Sumar SMTP es sumar secretos, cola y modo de
    falla; si hace falta, es una fase propia.
12. **Los adjuntos son documentación del proyecto, no un repositorio de archivos.** Hay
    cuota por proyecto y lista blanca de extensiones. No es Drive.

## Arquitectura y stack

> **Decisiones a validar** — recomendación con alternativa. Confirmá antes de la Fase 10.

La forma de la app no cambia: FastAPI + Jinja + HTMX server-rendered, un proceso, cero build
step. Lo que cambia es lo que la rodea y lo que el modelo sabe representar.

### Las cinco de infraestructura

**1. Identidad: sesión propia con tabla de sesiones, no cookie firmada.**
Contraseñas con **argon2id** (`argon2-cffi`), sesión como fila en la DB con token opaco en
cookie `HttpOnly; Secure; SameSite=Lax`. Unas 150 líneas.
*Por qué tabla:* una cookie firmada no se puede revocar antes de que expire — si echás a
alguien o se filtra una sesión, seguís esperando. Con tabla, "revocar ya" es un `DELETE`.
*Alternativa:* `fastapi-users`. Costo: dependencia grande que impone sus modelos, para
resolver un registro público que decidimos no tener.

**2. HTTPS: lo termina un proxy adelante, nunca la app.**
**Caddy** delante (HTTPS automático, renovación sola), la app sigue en `127.0.0.1:8000`. Así
la regla de CLAUDE.md se mantiene literal: el proceso Python nunca escucha en una interfaz
pública.
*Alternativa fuerte si el acceso es solo del equipo:* **Tailscale** (`tailscale serve`) —
certificado real, **cero puertos abiertos a internet**. Se combinan: Tailscale para el
equipo, Caddy público solo si el cliente necesita entrar a ver el informe.
*Descartado:* uvicorn con `--ssl-keyfile`. Mete TLS y renovación dentro del proceso de la app.

**3. Base: SQLite se queda, con WAL.** Con decenas de usuarios y carga dominada por lecturas,
alcanza de sobra y evita un servicio más. El límite honesto: **un escritor por vez**, y cada
edición recalcula el cronograma entero. Si aparecen esperas al guardar, ese es el síntoma y
ahí se migra a Postgres. *Los adjuntos no van en la base* (ver decisión 8).

**4. Migraciones: Alembic reemplaza a `migraciones.py`.**
v2 suma más de diez tablas y **dos migraciones de datos** (estados y responsables), y la base
ahora tiene trabajo de otras personas adentro. Un script aditivo sin versiones ni vuelta
atrás es el lugar equivocado para descubrir un error.
*Alternativa:* seguir a mano con backup previo. Defendible mientras seas el único que toca el
servidor; deja de serlo el día que no lo seas.

**5. El informe se imprime desde el navegador.** Una vista HTML con `@media print` (A4,
saltos controlados). Ctrl+P da un PDF idéntico al de una librería, con cero dependencias.
*Alternativa:* WeasyPrint, **solo si** hace falta generar el PDF sin una persona adelante.

### Las cinco de modelo

**6. Los pesos son % del padre, no % del proyecto.** Es la decisión más importante de este
bloque. Si cada tarea guardara su % absoluto del proyecto, agregar una sola tarea en
cualquier lado rompería la suma de todo el árbol. Guardando % del padre, **cada nivel suma
100 por su cuenta** y agregar una tarea solo obliga a rebalancear a sus hermanas. Tu ejemplo
sale solo: una etapa con 20% del proyecto y 5 subtareas que se reparten 100% entre ellas — la
subtarea al 20% del padre pesa 4% del proyecto. El peso absoluto se calcula multiplicando
hacia abajo desde la raíz, y es un dato derivado que nunca se guarda.

**El peso es nullable, y eso resuelve el 90% de la fricción:** `null` significa "repartí lo
que sobra en partes iguales entre las que están en null". Un nivel sin pesos cargados queda
automáticamente parejo y no molesta a nadie; si cargás 3 de 5, las otras 2 se reparten el
resto solas.

**La validación avisa, no bloquea.** Que la app te frene el guardado porque vas 97% mientras
estás cargando el proyecto es infumable. La grilla muestra el desvío por nivel en rojo y no
te deja **congelar una línea base ni emitir un informe** con los pesos abiertos, que es donde
el número realmente importa. Ese es el punto de control correcto.
*Alternativa:* peso automático por duración, sin intervención. Más simple, pero contradice el
pedido — y con razón: en tu Gantt de traspaso, "Firma del Acta" dura 1 día y vale muchísimo
más que 20 días de relevamiento.

**7. Los estados los define el usuario, pero le declaran su significado al motor.** Hoy
`EstadoTarea` es un enum de tres valores clavado en **9 archivos** (`vista`, `export`,
`plantilla`, `tasks`, `importar_diagnostico`, el router, `schemas`, el template y `models`),
y la app pregunta `estado == "hecha"` por todos lados. Si los estados pasan a ser texto libre
del usuario, eso se rompe entero.
La salida: tabla `Estado` por proyecto con `nombre`, `color`, `orden`, **`es_final`** y
`avance_sugerido`. Todo lo que hoy pregunta `== hecha` pasa a preguntar `estado.es_final`. Se
siembran los tres actuales para que ninguna base existente cambie de comportamiento.
*Consecuencia:* esto **corrige mi propio plan anterior**, que hacía derivar `estado` del %
de avance. Con estados definibles esa derivación no se sostiene. Quedan independientes:
`avance` es el número, `estado` es la etiqueta que elegís, y elegir un estado *sugiere* un
avance sin imponerlo.

**8. Los adjuntos van al filesystem, servidos por una ruta con permiso.** Nunca dentro de
`static/`: un archivo bajo `static/` es público para cualquiera que tenga la URL, y eso
saltea todo el modelo de permisos de la Fase 11. La DB guarda metadatos, el disco guarda el
archivo con **nombre generado** (el original queda solo como etiqueta), y la descarga pasa
por una ruta que verifica permiso en cada pedido.
*Consecuencia sobre el backup:* a partir de acá el backup son **dos cosas** (base + carpeta)
y el criterio de restauración de la Fase 13 tiene que cubrir ambas.
*Alternativa:* BLOB en SQLite. Simplifica el backup a un archivo, pero infla la base, rompe
el streaming y hace que cada backup copie todos los adjuntos de nuevo.

**9. Riesgos: tabla propia, no campos en `Task`.** Pediste un checkbox en la tarea y eso es lo
que se ve en la grilla, pero abajo hay una tabla `Riesgo` con `task_id` **nullable**. Dos
razones: un proyecto tiene riesgos que no cuelgan de ninguna tarea ("el cliente no libera el
ambiente"), y una tarea puede tener más de uno. El checkbox de la grilla es el atajo que crea
y muestra los riesgos de esa fila; la matriz necesita `probabilidad` × `impacto`, que un
booleano solo no da.
Escala **5×5** (severidad = P×I, cuatro zonas), que es lo estándar y lo que espera cualquiera
que haya visto una matriz de riesgo. *Alternativa:* 3×3, más rápido de llenar, pero apelmaza
todo en el medio.

**10. Los comentarios son texto plano.** Con markdown habría que renderizar HTML escrito por
otra persona, que es la receta del XSS almacenado. Texto plano con saltos de línea, autoescape
y límite de largo. Si algún día hace falta formato, se elige un renderer con sanitización y es
una decisión propia, no un `|safe` de apuro.

### Superficie de ataque

La que más cambia respecto de v1, y el motivo por el que multiusuario va antes que todo.

| Qué entra | Riesgo | Control |
|---|---|---|
| Login | Fuerza bruta, credential stuffing | argon2id, throttling progresivo por usuario+IP, mensaje único (no distingue usuario inexistente de contraseña mala) |
| Cookie de sesión | Robo, fijación | Token opaco de 32 bytes, `HttpOnly; Secure; SameSite=Lax`, **rota al iniciar sesión**, expira por inactividad y por antigüedad, revocable |
| Todo POST de la grilla | **CSRF** — hoy no hay defensa, y con cookies pasa a ser explotable | Token por sesión en `<meta>`, enviado por HTMX con `hx-headers`, exigido en todo verbo que no sea GET |
| `project_id` / `task_id` en la URL | **IDOR** — el riesgo más probable: adivinar el id de otro proyecto | Ninguna consulta parte de un id crudo. Dependencia `exige_lector/editor/dueño` que resuelve entidad **y** permiso juntos, o 404 (no 403: no confirma que exista) |
| **Archivos adjuntos** | Path traversal, XSS almacenado vía HTML/SVG, malware, llenar el disco | Nombre generado, fuera de `static/`, lista blanca de extensiones, límite por archivo y **cuota por proyecto**, `Content-Disposition: attachment` + `nosniff` para que **nada se renderice inline**, permiso verificado en cada descarga |
| Comentarios, notas, nombres | XSS almacenado — ahora los escribe *otro* | Texto plano, autoescape, límite de largo. La regla de nunca usar `\|safe` sobre datos de usuario pasa de higiene a control |
| Planilla `.xlsx` subida | Bomba de descompresión, archivo gigante | Ya se lee con `read_only`/`data_only`; sumar límite de tamaño y de filas **antes** de parsear |
| Link de informe (Fase 25, opcional) | Acceso sin cuenta | Token firmado con expiración, solo lectura, revocable, `X-Robots-Tag: noindex`, cada acceso registrado |
| El proceso mismo | Exposición accidental | Sigue bindeando `127.0.0.1`. El proxy es lo único que escucha afuera |

**Secretos:** aparece el primero de la vida del proyecto (`SECRET_KEY`). Va por variable de
entorno, se genera con `secrets.token_urlsafe(32)`, y **la app se niega a arrancar en modo
no-debug si falta o es el default**.

**CSP:** vendoreamos todo, así que `default-src 'self'` es alcanzable. Tres deudas concretas
la bloquean hoy: `templates/partials/tablero.html:78` y `:82` tienen `onclick=` inline, y
`templates/base.html:10` tiene un `<script>` inline. Van a un `.js` vendoreado. Los `style=`
del Gantt son geometría calculada y se quedan: `style-src 'self' 'unsafe-inline'`.

## Estructura del repo

Se mantiene `routers → services → engine | models/db`, y el motor sigue sin importar FastAPI
ni SQLModel. Lo nuevo:

```
app/
├── auth/                     # ★ identidad y permisos — cero lógica de negocio
│   ├── hash.py               # argon2id
│   ├── sesion.py             # crear/leer/revocar, cookie, rotación
│   ├── csrf.py
│   └── permisos.py           # exige_lector / exige_editor / exige_dueño
├── models.py                 # + Usuario, Sesion, Miembro, Cambio
├── models_trabajo.py         # Estado, Contacto, Riesgo, Comentario, Etiqueta, Adjunto
├── models_base.py            # LineaBase, LineaBaseTarea
├── engine/
│   └── comparar.py           # ★ desvío base vs actual — puro, sin DB
├── services/
│   ├── usuarios.py · miembros.py · auditoria.py
│   ├── pesos.py              # ★ puro: normalizar, peso absoluto, validar cierre
│   ├── estados.py · contactos.py
│   ├── riesgos.py            # incluye la matriz (severidad y zona: función pura)
│   ├── comentarios.py · adjuntos.py
│   ├── linea_base.py
│   ├── colores.py            # ★ puro: fila + modo → clase CSS
│   ├── exportar_excel.py     # ida y vuelta con el importador
│   └── informe.py            # arma el DTO; no renderiza
├── routers/
│   ├── auth.py · admin.py · miembros.py
│   ├── riesgos.py · comentarios.py · adjuntos.py
│   └── informe.py
├── templates/
│   ├── auth/ · riesgos/ · informe/
└── migrations/               # Alembic
var/adjuntos/                 # fuera del repo y fuera de static/
```

`app/migraciones.py` se elimina en la Fase 10, con su lógica en la primera revisión de Alembic.

## Fases

Ninguna fase se cierra si un archivo supera 300 líneas, si su control de seguridad quedó
afuera, o si el módulo nuevo no se testea aislado.

Un punto no negociable: **el bloque A entero va antes de exponer nada.** Una app a medio
autenticar en internet es peor que una app sin autenticar en localhost.

### Bloque A — Multiusuario (la puerta)

**Fase 10 — Identidad: usuarios, sesión y CSRF.** Alembic reemplaza a `migraciones.py`.
Modelos `Usuario` (mail único, hash argon2id, activo, `es_admin`, `debe_cambiar_password`) y
`Sesion`. Login con throttling progresivo. Cambio de contraseña obligatorio al primer
ingreso. Alta solo para el admin global. Token CSRF por sesión exigido en todo POST. **No se
expone nada todavía.**
*Hecho cuando:* un POST sin CSRF válido da 403 sin stack trace; el token de sesión rota al
login; la app no arranca en modo no-debug sin `SECRET_KEY`; el hash nunca aparece en un log
ni en una respuesta; `alembic upgrade head` reproduce la base desde cero **y** actualiza una
base v1 existente sin perder datos.

**Fase 11 — Autorización: dueño y miembros.** `Project` gana dueño; tabla `Miembro` (rol
dueño/editor/lector). Las dependencias `exige_lector/editor/dueño` resuelven proyecto y
permiso en un solo paso y **ninguna ruta vuelve a partir de un id crudo**. El home lista solo
tus proyectos. Modo lectura real: sin celdas editables y con el endpoint rechazando la
escritura aunque armes el POST a mano.
*Hecho cuando:* hay un test por cada verbo mutante que confirma 404 para un usuario ajeno y
403 para un lector — la UI escondida no cuenta como control; un proyecto no queda huérfano;
borrar un usuario no borra sus proyectos.

**Fase 12 — Trabajo simultáneo sin pisarse.** SQLite en WAL con `busy_timeout`. `Task` gana
`version`: la celda manda la versión que leyó y, si no coincide, devuelve 409 con la fila
recargada y un aviso claro — **nunca un guardado silencioso encima**. Tabla `Cambio` (quién,
cuándo, tarea, campo, de → a) escrita desde los services. Vista de historial.
*Hecho cuando:* un test simula dos ediciones concurrentes y la segunda es rechazada, no
aplicada; el historial reconstruye la vida de una tarea; la auditoría no se puede editar
desde la app.

**Fase 13 — Exposición segura.** Proxy adelante (Caddy o Tailscale) con la app todavía en
`127.0.0.1`. HSTS, `X-Content-Type-Options`, `Referrer-Policy` y CSP `default-src 'self'` —
lo que exige pagar las tres deudas de JS inline. Límite de tamaño y de filas en la subida de
planillas. Backup automático con rotación y **restauración probada**.
`README-OPERACION.md`: levantar, actualizar, rotar `SECRET_KEY`, restaurar, dar de baja.
*Hecho cuando:* el puerto de la app no responde desde otra máquina; sin advertencias de CSP
en consola; un backup se restaura **de verdad** en una máquina limpia y la app levanta con
esos datos; `/security-review` corrido sobre el diff completo del bloque A. Recién con esto
cerrado se comparte la URL.

### Bloque B — El modelo de trabajo

**Fase 14 — Personas: responsable de verdad.** Hoy `responsable` es texto libre, así que
"Ariel", "ariel" y "A. Clerici" son tres personas distintas. Tabla `Contacto` por proyecto
(nombre, mail, opcionalmente vinculado a un `Usuario`), y `responsable_id` en **proyecto,
etapa y tarea**. Migración que convierte los textos actuales en contactos, deduplicando.
Selector en la grilla, no campo libre. Vista "mis tareas". El responsable de una etapa se
muestra junto al rollup, y el resumen avisa qué etapas no tienen.
*Ojo con la distinción:* el **dueño** es un permiso, el **responsable** es una rendición de
cuentas. No son lo mismo y no tienen por qué ser la misma persona.
*Hecho cuando:* ningún responsable queda como texto suelto tras la migración; un contacto sin
cuenta funciona igual que uno con cuenta; borrar un contacto usado pide reasignación.

**Fase 15 — Estados definibles. ✔** Tabla `Estado` por proyecto (nombre, color, orden,
`es_final`, `avance_sugerido`), sembrada con los tres actuales. Los 9 archivos que hoy
preguntan `== "hecha"` pasan a preguntar `estado.es_final`. ABM de estados para el dueño;
borrar uno en uso obliga a reasignar.
*Hecho cuando:* una base existente migra sin que cambie el comportamiento de ninguna tarea;
un proyecto con estados propios calcula avance, próximo hito y export igual de bien; no queda
ninguna comparación contra el string "hecha" en el código.

**Fase 16 — Pesos por etapa y por tarea. ✔** `Task` gana `peso` (nullable, % del padre).
`services/pesos.py` **puro, sin sesión**: normaliza un nivel, calcula el peso absoluto
multiplicando hacia abajo, y valida el cierre por nivel. Columna **Peso** en la grilla, con el
% del proyecto al lado como dato derivado. El nivel que no cierra se marca en rojo con el
faltante o el sobrante. Botones "repartir en partes iguales" y "repartir por duración" por
nivel.
*Cuidado con el default:* el reparto parejo le da a un hito de 1 día el mismo peso que a una
tarea de 30. Es un punto de partida, no una respuesta.
*Hecho cuando:* el módulo se testea sin DB con nivel vacío, parcialmente cargado, que se pasa
de 100, con hitos y con árbol de 3 niveles; agregar una tarea a un nivel ya cerrado avisa en
vez de romper; los pesos absolutos de todas las hojas suman 100 cuando todos los niveles
cierran.

**Fase 17 — Línea base. ✔** `LineaBase` y `LineaBaseTarea` (inicio, fin, duración, ámbito,
**peso** congelados). `engine/comparar.py` puro: desvío en días hábiles con signo por tarea y
por ámbito. Congelar exige que los pesos cierren. Columna **Desvío** en la grilla y barra base
en gris debajo de la actual.
*Hecho cuando:* el motor compara dos cronogramas sin DB, con tests para tarea atrasada,
adelantada, sin cambios, nueva y borrada; congelar no altera ninguna fecha del cronograma
vivo; un proyecto sin línea base sigue funcionando y no muestra desvíos vacíos.

**Fase 18 — Avance real y ponderado. ✔** `Task` gana `avance` (0-100), `inicio_real` y
`fin_real`. El avance del proyecto pasa a ser **Σ (peso absoluto × avance)** sobre las hojas,
que es la razón de ser de la Fase 16: hoy "0 de 31 hechas" trata igual una firma de acta que
120 días de acompañamiento. El resumen distingue **avance planificado a la fecha de corte**
(contra la línea base) del **avance real**, que es la única forma de que un 45% signifique
algo.
*Hecho cuando:* el avance ponderado tiene tests propios (sin empezar, a mitad, terminado, sin
pesos y sin línea base); una tarea al 100% sin `fin_real` lo toma del cronograma; el conteo
simple sigue disponible como dato secundario.

### Bloque C — Riesgos y contenido

**Fase 19 — Riesgos: registro y cuadrante. ✔** Tabla `Riesgo` (proyecto, `task_id` nullable,
descripción, probabilidad 1-5, impacto 1-5, mitigación, responsable, estado). Checkbox en la
grilla que marca la fila y abre el detalle; ⚠ visible en la fila que tiene riesgos. Cuadrante
5×5 pintado con CSS Grid server-side —igual que el Gantt, sin librería de gráficos— con
severidad = P×I y cuatro zonas. La función que da severidad y zona es pura y se testea sola.
*Hecho cuando:* un riesgo sin tarea funciona igual que uno con tarea; el cuadrante ubica cada
riesgo en su celda y los tests cubren los cuatro bordes de zona; el cuadrante se imprime en
blanco y negro sin perder la información (color **más** número, no color solo).

**Fase 20 — Comentarios con categoría y tags.** Tabla `Comentario` (tarea o proyecto, autor,
fecha, texto plano, editado) con **una categoría** de un vocabulario que define el dueño
(Decisión / Riesgo / Bloqueo / Avance por default) y **N tags** libres reutilizables con
color. Filtro por categoría y por tag. El informe levanta los comentarios desde el corte
anterior.
*Hecho cuando:* el texto se guarda y se muestra plano y escapado, con salto de línea
respetado y sin ningún `|safe`; borrar una categoría en uso obliga a reasignar; un lector
puede leer comentarios pero no escribirlos.

**Fase 21 — Adjuntos.** Tabla `Adjunto` (tarea o proyecto, nombre original, nombre en disco,
tamaño, mime, quién, cuándo). Archivos en `var/adjuntos/`, **fuera de `static/`**, con nombre
generado; descarga por ruta que verifica permiso en cada pedido, con
`Content-Disposition: attachment` y `nosniff`. Lista blanca de extensiones, límite por archivo
y cuota por proyecto.
*Hecho cuando:* un test confirma que un no-miembro con la URL exacta del archivo recibe 404;
un `.svg` y un `.html` subidos **se descargan, no se renderizan**; un nombre con `../` no
escapa del directorio; superar la cuota da un error claro; y el backup de la Fase 13
**se re-verifica cubriendo base + carpeta de adjuntos**, con restauración probada de las dos.

### Bloque D — Vista y salida

**Fase 22 — Gantt: nivel de detalle, filtro por etapa y colores. ✔** Nivel de detalle (todo /
hasta nivel N / solo etapas) y filtro por etapa, **en la URL** (`?vista=etapas&etapa=2`) para
que el estado sea compartible y sin JS. Selector de modo de color: criticidad / estado /
ámbito / avance — excluyentes, porque dos criterios de color a la vez dan barro. El % de
avance se pinta como **relleno dentro de la barra**, que es ortogonal al tono, así siempre ves
progreso más una dimensión. `services/colores.py` puro: fila + modo → clase CSS, sin estilos
inline (la CSP de la Fase 13 no los permitiría).
*Hecho cuando:* el modo de color se testea como función pura; la vista "solo etapas" de un
proyecto de 200 tareas entra en una pantalla; ningún color es la única señal (hay etiqueta o
patrón), y la paleta se distingue impresa en blanco y negro.

**Fase 23 — Export a Excel, con vuelta. ✔** `services/exportar_excel.py` con openpyxl (ya es
dependencia): la grilla completa —WBS, tarea, responsable, predecesoras en notación WBS,
días, opt/pes, inicio, fin, crít., ámbito, peso, estado, avance, riesgo— más fechas base y
desvío cuando hay línea base. **El contrato es la ida y vuelta:** exportar un proyecto e
importar ese mismo archivo tiene que reproducirlo igual.
*Nota:* se genera `.xlsx`, no `.xls`. El `.xls` binario viejo necesitaría una librería
abandonada y Excel abre `.xlsx` desde 2007 sin chistar.
*Hecho cuando:* hay un test de ida y vuelta que exporta un proyecto con dependencias, hitos,
pesos y ámbitos, lo reimporta y compara el resultado tarea por tarea; el archivo abre en
Excel real sin advertencias.

**Fase 24 — El informe. ✔** `/proyectos/{id}/informe?corte=YYYY-MM-DD`, accesible desde rol
lector. `services/informe.py` arma el DTO —datos, no HTML—: portada, resumen ejecutivo
(ventana por ámbito, avance real vs planificado, desvío contra la base, próximo hito), tareas
atrasadas y en riesgo, hitos con fecha base y proyectada, **cuadrante de riesgos**,
**comentarios desde el corte anterior**, qué se movió según la auditoría, y el **Gantt en
vista de etapas** —que es lo que lo hace entrar en A4—. CSS `@media print`.
*Hecho cuando:* un test compara los números del informe con los de la grilla sobre el mismo
proyecto y exige que coincidan; el PDF impreso entra en A4 sin cortar barras ni tablas;
`services/informe.py` no genera HTML; no se puede emitir con los pesos abiertos.

**Fase 25 (opcional) — Link de solo lectura para el cliente.** Link firmado, con vencimiento
y revocable, que muestra el informe sin cuenta. Es comodidad real y superficie nueva a la vez:
se hace solo si lo pedís, con token de alta entropía, expiración corta por default, revocación
desde la app, `noindex`, sin exponer más que ese informe, y cada acceso registrado.

## Camino corto

Cuatro fases de infraestructura antes de ver algo nuevo en pantalla es mucho pedir. Estas se
pueden **adelantar sin tocar la postura de seguridad**, porque no dependen de que haya
usuarios y no exponen nada:

**16 (pesos) · 15 (estados) · 19 (riesgos y cuadrante) · 22 (Gantt por etapas y colores) ·
23 (export a Excel)**

Las que **sí** necesitan el bloque A cerrado, porque sin autor no significan nada: 14
(responsables como personas), 20 (comentarios), 21 (adjuntos), y todo el informe.

**Estado: hecho el camino corto más el bloque de informes** (fases 15, 16, 17, 18, 19,
22, 23 y 24, marcadas con ✔ arriba).
Ariel decidió seguir monousuario por ahora, así que el bloque A sigue pendiente y la app
no salió de `127.0.0.1`. Cuando entre el equipo, se retoma por la Fase 10 y el orden del
plan vuelve a mandar.

## Lo que este plan deja explícitamente afuera

El cerco contra el scope creep: sin auto-registro ni OAuth; sin recuperación de contraseña
por mail; sin permisos por tarea o por columna; sin colaboración en tiempo real; sin
notificaciones; sin recursos ni nivelación de carga; sin markdown en comentarios; sin
versionado de adjuntos; sin app móvil; sin API pública. Cada uno es una fase propia contra
este plan, no un agregado dentro de otra.

## Prompts para Code

Uno por fase, en orden; cada uno asume el anterior cerrado. Todos comparten estos criterios,
que no se repiten abajo: ningún archivo supera 300 líneas, todo módulo nuevo se testea
aislado, input validado con Pydantic en el borde, y sin `|safe` sobre datos de usuario.

**Fase 10** — Leé CLAUDE.md, PLAN-DE-OBRA.md y PLAN-DE-MEJORAS.md. Reemplazá
`app/migraciones.py` por Alembic (primera revisión = esquema actual; `alembic upgrade head`
tiene que actualizar una base v1 existente sin perder datos, probalo). Después `app/auth/`:
`hash.py` (argon2id con argon2-cffi), `sesion.py` (tabla `Sesion`, token de
`secrets.token_urlsafe(32)`, cookie HttpOnly/Secure/SameSite=Lax, rotación al login,
expiración por inactividad y por antigüedad, revocación) y `csrf.py` (token por sesión en
`<meta>`, HTMX lo manda con `hx-headers` global, dependencia que lo exige en todo verbo no
GET). Modelo `Usuario`. Routers de login/logout/cambio de contraseña y de alta para el admin.
Throttling progresivo por usuario+IP y mensaje único ante credenciales inválidas.
*Aceptación:* POST sin CSRF da 403 sin stack trace; el token rota al login; la app no arranca
en modo no-debug sin `SECRET_KEY` o con el default; el hash nunca sale en log ni respuesta.

**Fase 11** — `Project` gana dueño; tabla `Miembro` (dueño/editor/lector). En
`app/auth/permisos.py`, dependencias `exige_lector/editor/dueño` que resuelven proyecto y
permiso en un paso y devuelven **404** (no 403) al no-miembro. Recorré **todas** las rutas de
proyectos, tareas, dependencias, import y export: ninguna puede partir de un id crudo. Home
filtrado por membresía. Modo lectura real (endpoint que rechaza, no solo UI escondida).
Pantalla de miembros.
*Aceptación:* un test por verbo mutante con 404 para ajeno y 403 para lector; un proyecto no
queda sin dueño; borrar un usuario no borra sus proyectos.

**Fase 12** — SQLite en WAL con `busy_timeout`. `Task.version` incremental; las celdas mandan
la versión leída y una versión vieja da 409 con la fila recargada y aviso claro, nunca
guardado encima. Tabla `Cambio` escrita desde los services. Historial por proyecto, paginado.
*Aceptación:* test de dos ediciones concurrentes donde la segunda se rechaza y no se aplica;
el historial reconstruye la vida de una tarea; no hay ruta que edite o borre un `Cambio`.

**Fase 13** — Proxy adelante (Caddyfile o `tailscale serve`) con la app en 127.0.0.1.
Middleware de headers: HSTS, X-Content-Type-Options, Referrer-Policy, CSP
`default-src 'self'; style-src 'self' 'unsafe-inline'`. Sacá el JS inline: `onclick` de
`templates/partials/tablero.html` líneas 78 y 82, y el `<script>` de `templates/base.html`.
Límite de tamaño y filas en la subida de planillas, rechazando antes de parsear. Backup con
`VACUUM INTO` y rotación, más `README-OPERACION.md`.
*Aceptación:* el puerto de la app no responde desde otra máquina; sin advertencias de CSP en
consola; un backup restaurado en máquina limpia levanta con los datos; corré
`/security-review` sobre el diff del bloque A y resolvé lo que salga.

**Fase 14** — Tabla `Contacto` por proyecto (nombre, mail, `usuario_id` nullable) y
`responsable_id` en `Project` y `Task`. Migración que convierte los `responsable` de texto en
contactos deduplicando por nombre normalizado. Selector en la grilla en vez de campo libre.
Vista "mis tareas". Responsable de etapa visible en el rollup; el resumen avisa etapas sin
responsable.
*Aceptación:* tras migrar no queda ningún responsable como texto suelto; un contacto sin
cuenta funciona igual que uno con cuenta; borrar un contacto en uso pide reasignación.

**Fase 15** — Tabla `Estado` por proyecto (nombre, color, orden, `es_final`,
`avance_sugerido`), sembrada con pendiente/en curso/hecha. Reemplazá **todas** las
comparaciones contra el string "hecha" por `estado.es_final` — están en `services/vista.py`,
`services/export.py`, `services/plantilla.py`, `services/tasks.py`,
`services/importar_diagnostico.py`, `routers/tasks.py`, `schemas.py`,
`templates/partials/tablero.html` y `models.py`. ABM de estados para el dueño; borrar uno en
uso obliga a reasignar.
*Aceptación:* una base v1 migra sin cambiar el comportamiento de ninguna tarea; un proyecto
con estados propios calcula avance, próximo hito y export igual; no queda ninguna comparación
contra "hecha" en el código.

**Fase 16** — `Task.peso` nullable, interpretado como **% del padre**; `null` significa
"repartir en partes iguales lo que sobra entre las null". `services/pesos.py` **puro, sin
Session**: normalizar un nivel, peso absoluto multiplicando desde la raíz, y validar cierre
por nivel. Columna Peso en la grilla con el % del proyecto derivado al lado; nivel que no
cierra marcado en rojo con faltante o sobrante. Botones por nivel "repartir en partes
iguales" y "repartir por duración". **La validación avisa, no bloquea** el guardado.
*Aceptación:* tests sin DB para nivel vacío, parcial, pasado de 100, con hitos y árbol de 3
niveles; agregar una tarea a un nivel cerrado avisa en vez de romper; con todos los niveles
cerrados los pesos absolutos de las hojas suman 100.

**Fase 17** — `LineaBase` y `LineaBaseTarea` (inicio, fin, duración, ámbito y peso
congelados) en `app/models_base.py`. `app/engine/comparar.py` en Python puro, sin FastAPI ni
SQLModel: recibe cronograma actual y congelado y devuelve desvío en días hábiles con signo por
tarea más agregados por ámbito. Congelar/listar/marcar vigente (solo dueño), exigiendo que los
pesos cierren. Columna Desvío en la grilla y barra base en gris en el Gantt.
*Aceptación:* tests del engine sin DB para atrasada, adelantada, sin cambios, tarea nueva y
tarea borrada; congelar no cambia ninguna fecha viva; sin línea base todo funciona igual.

**Fase 18** — `Task` gana `avance` (0-100), `inicio_real`, `fin_real`. Avance del proyecto =
Σ (peso absoluto × avance) sobre las hojas; el avance de una etapa, lo mismo normalizado a su
subárbol. Sumá al resumen el avance planificado a la fecha de corte contra la línea base
vigente, junto al real. Elegir un estado sugiere un avance sin imponerlo (los estados y el
avance quedan independientes).
*Aceptación:* tests del avance ponderado (sin empezar, a mitad, terminado, sin pesos, sin
línea base); tarea al 100% sin `fin_real` lo toma del cronograma; el conteo simple queda como
dato secundario.

**Fase 19** — Tabla `Riesgo` (proyecto, `task_id` **nullable**, descripción, probabilidad
1-5, impacto 1-5, mitigación, responsable, estado). Checkbox en la grilla que marca la fila y
abre el detalle, con ⚠ en las filas que tienen riesgos. Cuadrante 5×5 con CSS Grid
server-side, sin librería de gráficos; severidad = P×I con cuatro zonas, calculadas por una
función pura.
*Aceptación:* riesgo sin tarea funciona igual que con tarea; tests de los cuatro bordes de
zona; el cuadrante impreso en blanco y negro no pierde información (color **más** número).

**Fase 20** — Tabla `Comentario` (tarea o proyecto, autor, fecha, texto plano, editado), una
`categoria` de vocabulario definido por el dueño (Decisión / Riesgo / Bloqueo / Avance por
default) y N `Etiqueta` libres con color. Filtro por categoría y por tag. **Texto plano, sin
markdown.**
*Aceptación:* el texto se guarda y muestra escapado, respetando saltos de línea, sin ningún
`|safe`; borrar una categoría en uso obliga a reasignar; un lector lee pero no escribe.

**Fase 21** — Tabla `Adjunto` (tarea o proyecto, nombre original, nombre en disco, tamaño,
mime, quién, cuándo). Archivos en `var/adjuntos/`, **fuera de `static/`**, con nombre
generado; el original se guarda solo como etiqueta. Descarga por ruta que verifica permiso en
cada pedido, con `Content-Disposition: attachment` y `X-Content-Type-Options: nosniff`. Lista
blanca de extensiones, límite por archivo y cuota por proyecto.
*Aceptación:* test de que un no-miembro con la URL exacta recibe 404; un `.svg` y un `.html`
se descargan y **no se renderizan**; un nombre con `../` no escapa del directorio; superar la
cuota da error claro; re-verificá el backup de la Fase 13 cubriendo base **y** carpeta de
adjuntos, con restauración probada de ambas.

**Fase 22** — Nivel de detalle (todo / hasta nivel N / solo etapas) y filtro por etapa **en
query params**, sin estado en el cliente. Selector de modo de color excluyente: criticidad /
estado / ámbito / avance, con el % pintado como relleno dentro de la barra. `services/colores.py`
puro: fila + modo → clase CSS; nada de estilos inline (la CSP no los permite).
*Aceptación:* el modo de color se testea como función pura; "solo etapas" de un proyecto de
200 tareas entra en una pantalla; ningún color es la única señal y la paleta se distingue
impresa en blanco y negro.

**Fase 23** — `services/exportar_excel.py` con openpyxl: grilla completa (WBS, tarea,
responsable, predecesoras en notación WBS, días, opt/pes, inicio, fin, crít., ámbito, peso,
estado, avance, riesgo) más fechas base y desvío si hay línea base. Genera `.xlsx`.
*Aceptación:* test de **ida y vuelta** que exporta un proyecto con dependencias, hitos, pesos
y ámbitos, lo reimporta con el importador existente y compara tarea por tarea; el archivo abre
en Excel real sin advertencias.

**Fase 24** — `/proyectos/{id}/informe?corte=YYYY-MM-DD` desde rol lector.
`services/informe.py` arma el DTO (datos, no HTML): portada, resumen ejecutivo (ventana por
ámbito, avance real vs planificado, desvío contra la base, próximo hito), atrasadas y en
riesgo, hitos base vs proyectados, cuadrante de riesgos, comentarios desde el corte anterior,
qué se movió según la auditoría, y el Gantt en vista de etapas. Plantillas en
`templates/informe/` con CSS `@media print` A4 y saltos controlados.
*Aceptación:* test que compara los números del informe con los de la grilla y exige
coincidencia; el PDF entra en A4 sin cortar barras ni tablas; `informe.py` no genera HTML; no
se emite con los pesos abiertos.

## Cambios a CLAUDE.md

La sección **Seguridad** de CLAUDE.md dice hoy que la app bindea solo `127.0.0.1` y que
exponerla exige auth + HTTPS previos. Esa regla no se toca ahora: **se cumple recién al cerrar
la Fase 13**, y ahí se reescribe así (texto a aplicar en esa fase, no antes):

> - La app **sigue bindeando solo `127.0.0.1`**: el TLS lo termina el proxy de adelante, y el
>   proceso Python nunca escucha en una interfaz pública.
> - **Ninguna consulta parte de un id crudo.** Toda ruta de proyecto pasa por
>   `exige_lector/editor/dueño`, que resuelve entidad y permiso juntos y responde 404 —no
>   403— ante un no-miembro. Esconder el botón en la UI no es un control.
> - Contraseñas con **argon2id**, nunca en logs ni en respuestas. Sesiones como fila en la DB,
>   con token opaco, revocables, que rotan al iniciar sesión.
> - **Todo verbo que no sea GET exige token CSRF válido.**
> - **Los archivos subidos nunca se sirven desde `static/` ni se renderizan inline:** nombre
>   generado, ruta con permiso, `Content-Disposition: attachment` y `nosniff`.
> - `SECRET_KEY` por variable de entorno; la app no arranca en modo no-debug sin ella.
> - El resto sigue vigente: Pydantic en el borde, el grafo como input hostil, ORM sin SQL a
>   mano, autoescape sin `|safe`, sin secretos en el repo, sin stack traces al navegador, la
>   DB fuera de git.

También se suma a *Reglas del motor* que **el peso es % del padre y el avance es ponderado**,
y a *La grilla* las columnas nuevas (Peso, Desvío, Avance, Riesgo).

## Riesgos

| Riesgo | Mitigación |
|---|---|
| **Exponer la app con el bloque A a medio hacer.** El más grave y el más fácil de cometer: alcanza con querer mostrarle algo a alguien un martes. | El orden de fases es la mitigación y la Fase 13 es una puerta explícita: hasta que no cierre, la URL no se comparte. Escrito acá para que no dependa de acordarse. |
| **Adjuntos servidos desde `static/`.** Es el error de una línea que anula todo el modelo de permisos: cualquiera con la URL se lleva el archivo de cualquier cliente. | Decisión 8 y criterio de hecho de la Fase 21: hay un test que exige 404 para un no-miembro con la URL exacta. |
| **IDOR.** Con ids secuenciales, el modo de falla probable no es un atacante: es un miembro cambiando un número y viendo el proyecto de otro cliente. | Fase 11 revisa *todas* las rutas y exige un test por verbo, no una inspección visual. |
| **Pérdida silenciosa de ediciones.** Rompe la confianza más rápido que cualquier bug de cálculo, y sin dejar rastro. | Bloqueo optimista con 409 visible (Fase 12) en vez de last-write-wins, más auditoría. |
| **Los pesos se vuelven una carga burocrática** y el usuario los abandona a medio cargar. | `peso` nullable con reparto automático: un nivel sin tocar queda parejo y no molesta. La validación avisa y solo bloquea donde el número importa de verdad (línea base e informe). |
| **Estados definibles rompen el cálculo.** El enum está clavado en 9 archivos y la app pregunta `== "hecha"` por todos lados. | `es_final` como contrato explícito entre el estado del usuario y el motor, más el criterio de que no quede ninguna comparación contra el string en el código. |
| **Dos migraciones de datos sobre trabajo ajeno** (responsables y estados). En v1 un error costaba tu base; ahora cuesta la de otros. | Alembic desde la Fase 10, backup probado en la 13 —que va antes que ambas a propósito— y cada migración con test sobre una base poblada. |
| **El informe miente.** Si sus números no coinciden con la grilla, el daño es peor que no tener informe: se manda a un cliente. | Criterio de hecho de la Fase 24: un test compara ambas salidas y exige coincidencia. |
| **Un escritor por vez en SQLite.** | Aceptado para decenas de usuarios. El síntoma está nombrado (esperas al guardar) y el upgrade a Postgres es una decisión ya tomada, no una investigación pendiente. |
| **Backup que nunca se probó**, ahora con dos piezas (base + adjuntos). | El criterio no es "el backup corre": es "se restauró en una máquina limpia y la app levantó con los archivos". |
