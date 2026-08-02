# Para retomar

Nota corta para abrir mañana y saber dónde estamos. El detalle está en
`PLAN-DE-OBRA.md` (v1) y `PLAN-DE-MEJORAS.md` (v2); esto es solo el punto de entrada.

## Levantar la app

En PowerShell, desde la carpeta del proyecto (acordate: `;` y no `&&`):

```powershell
git pull
uv sync
uv run python -m app
```

Después, `http://127.0.0.1:1983` (el puerto es fijo — el año de WarGames — y se
cambia con `WOPR_PORT`).

**Ojo (30/07/2026):** el Control de Aplicaciones de Windows está bloqueando cada vez
más ejecutables de desarrollo: primero `uv.exe`, después también el `python.exe`
del `.venv` («una directiva bloqueó este archivo»). El intérprete base de uv sí
corre; mientras tanto la app levanta así (PowerShell):

```powershell
$env:PYTHONPATH = ".venv\Lib\site-packages"
& "$env:APPDATA\uv\python\cpython-3.14-windows-x86_64-none\python.exe" -m app
```

La solución de fondo es tuya: permitir estos binarios en Seguridad de Windows
(Control de aplicaciones y navegador) o revisar por qué la directiva se activó.

## La lista de pendientes (al 30/07/2026)

Todo lo accionable del plan está **hecho y commiteado** (bloque E + fase 29 completos,
513 tests en verde). Lo que queda depende de Ariel:

**Decisiones e insumos:**

- [ ] **Columnas por defecto de la grilla** — decir cuáles se usan de verdad; es un
      cambio de una línea.
- [ ] **Riesgos a fondo** — definir el alcance charlando (plan de respuesta, riesgo
      residual, disparadores, vínculo con tareas de mitigación). No arrancar sin eso.
- [ ] **El ejemplo de Word** para diseñar ese import (quedó de pasarlo).
- [ ] **¿Entra el equipo?** — la decisión que destraba las 6 fases de multiusuario
      (bloque A + comentarios + adjuntos) y la 25 opcional.

**Mantenimiento / higiene:**

- [ ] Destrabar el **Control de Aplicaciones de Windows** que bloquea `uv.exe` y el
      Python del venv (mientras tanto: el workaround de «Levantar la app»).
- [ ] **Rotar la GROQ_API_KEY** (quedó pegada en el chat de trabajo) y actualizar
      el `.env` — un minuto en console.groq.com.
- [ ] Abrir **`wopr-gantt-demo.xlsx`** (en Descargas) y confirmar que Excel lo abre
      sin advertencias.
- [ ] Decidir si **pushear la rama** — hoy todos los commits viven solo en esta
      máquina, sin respaldo remoto.

## Dónde quedó

Todo lo que funciona con un solo usuario está hecho: **471 tests en verde**. El ciclo
cierra de punta a punta — cargás o importás, planificás, congelás lo aprobado, medís
el desvío y emitís el informe. Las etapas ahora se **pliegan y despliegan** con el
chevron (▾/▸) de la fila: es orden visual, viaja en la mirada y no toca los totales.

De la pasada de experiencia de usuario (pedida por Ariel):

- **La vista se recuerda por proyecto** (columnas, detalle, color, plegadas, flechas):
  salir y volver ya no la resetea. Se guarda en `Project.vista`; un link con
  parámetros la pisa y queda guardada.
- **El árbol se lee por color**: etapas en azul de acento (negrita, letra más grande,
  fondo azulado), críticas en el mismo rojo que su barra (título, WBS y filo
  izquierdo), tareas comunes en blanco, terminadas en gris tachado.
- **Las flechas de dependencias se apagan** con el tilde «Flechas» de la barra de
  vista (punto 4 de esta lista): con muchas dependencias eran ruido.
- **El scroll ya no salta**: borrar una fila o editar una celda conserva la posición
  vertical de la página y la horizontal del timeline y de la grilla.
- **Las cabeceras quedan a la vista al bajar** (punto 1 de esta lista): fijadas por
  JS con translateY — sticky puro no puede porque viven dentro de dos contenedores
  con scroll horizontal, y cualquier overflow ≠ visible se captura el sticky.
- Verificado todo con navegador real (Playwright + Chrome del sistema, efímero):
  clics en la barra de vista, chevron, borrado midiendo scroll, todas las páginas y
  los exports en 200, cero errores de consola.

Lo último de la sesión fue una **revisión de código del repo entero con arreglos**.
Los que importan:

- **Editar una celda ya no borra lo de las columnas ocultas.** Antes, con la vista
  por defecto, tocar un título reseteaba criticidad, peso, rango y ámbito de esa
  fila (y con Predec. oculta, borraba sus dependencias). Ahora lo que no viaja en
  el form se conserva.
- **Se acabó el SNET fantasma:** guardar una fila ya no ancla la tarea a su fecha
  calculada; mover el arranque del proyecto vuelve a mover todo.
- **Bug 3 de esta lista (la barra de vista) arreglado** — detalle abajo.
- Un XSS en los `confirm()` de borrado (nombre interpolado en JS inline), el WBS
  duplicado que desviaba dependencias, el import que cortaba en 400 filas en
  silencio, y una tanda de menores. Todo con test.

## Lo que marcó Ariel para mañana

**1. Se pierden los nombres de las columnas al bajar** — **RESUELTO.** No fue con
`position: sticky` como decía esta nota (los contenedores con scroll horizontal lo
capturan), sino con translateY desde `grilla.js`, clavado al scroll de la página.
Verificado con navegador real.

**2. Riesgos: revisar la sección más a fondo** (a definir con Ariel). Hoy tiene
registro, cuadrante 5×5 y el tilde en la grilla. Falta charlar qué le falta: puede ser
el plan de respuesta (evitar / mitigar / transferir / aceptar), riesgo residual
—probabilidad e impacto *después* de mitigar, que es lo que se reporta—, disparadores,
fecha de revisión, o vincular el riesgo a una tarea de mitigación del cronograma.
**No arrancar sin definirlo con él.**

**3. La barra de vista entera no funciona** — **RESUELTO.** El form de la vista se
movió afuera del contenedor con `hx-vals` (que pisaba sus valores en htmx 2.0.7), con
un hidden de `columnas` para que «ninguna tildada» siga siendo una elección válida.
De paso, el form de «Inicio del proyecto» —que también estaba afuera del contenedor y
perdía la mirada al usarlo— ahora la lleva consigo. Verificado con clics reales
(Playwright): Detalle filtra, Color aplica, Columnas prende y apaga.

**4. Poder apagar las flechas de dependencias** — **RESUELTO.** Tilde «Flechas» en la
barra de vista, un control más de la mirada: viaja en la URL, persiste con la vista
del proyecto y por default están prendidas.

## Lo primero que conviene mirar

1. **Abrí tu proyecto y mirá el Gantt.** Es lo que estuvimos arreglando y no lo viste
   funcionando todavía.
2. **Probá el selector de Columnas** (arriba de la grilla, dice «Columnas (6 de 13)»)
   y **arrastrá el borde de la columna Tarea**. Los anchos se guardan por proyecto.
3. **Decidí las columnas por defecto.** Hoy vienen Resp., Predec., Días, Inicio, Fin y
   Avance. Los títulos ya no se cortan (la columna Tarea no se encoge por debajo de su
   ancho calculado), pero con todas esas prendidas las columnas de la derecha pueden
   quedar detrás del scroll del panel. Si me decís cuáles usás de verdad, achico el
   default. Es cambiar una línea.

## Lo que viene: bloque E (plan de mejoras)

Las mejoras chicas que pediste quedaron planificadas como **fases 26-28 del bloque E** en
`PLAN-DE-MEJORAS.md`, y **el bloque está completo**:

- **26** — el export a Excel trae una segunda hoja «Gantt» con el timeline pintado (por
  día hábil, o por semana si el proyecto es largo), mismos colores que la app, sin tocar
  la ida y vuelta del import (la hoja usa «Código» y no «WBS» a propósito, para que el
  importador no la confunda con el plan). Hay una muestra en tu carpeta de Descargas:
  `wopr-gantt-demo.xlsx` — falta que la abras en Excel y confirmes que abre limpia.
- **27** — `python -m app` en el puerto fijo **1983**, 127.0.0.1 clavado en el código.
- **28** — la verificación manual con navegador pasó a `tests/navegador/` (Playwright
  sobre tu Chrome, `uv sync --group navegador`); sin Playwright la suite normal ni se
  entera. El bug 3 ya tiene su test de clic real.

Dato tuyo que sigue faltando: **qué columnas querés por defecto** en la grilla.

La **Fase 29 — Asistente con IA está completa** (Groq, capa gratuita, key en el `.env`
de la raíz — fuera de git —, modelo configurable vía `WOPR_IA_MODELO`):

- **29a** — botón «Asistente IA» arriba de la grilla: análisis y recomendaciones,
  solo lectura.
- **29b** — le pedís cambios en lenguaje natural («agregá una tarea de 3 días en la
  Etapa 3 después del handover»), te muestra las acciones propuestas y **nada se
  aplica hasta que confirmás**. Contrato cerrado (crear / modificar / cambiar
  predecesoras), validado con Pydantic, aplicado solo vía services — un ciclo o un
  WBS inexistente rebota con aviso. Verificado con el modelo real de punta a punta:
  propuso `Crear «Prueba de estrés» bajo 3 (3d, después de 3.5)` y la aplicó bien.

Ojo: la key se pegó en el chat de trabajo — si querés máxima higiene, rotala en
console.groq.com y actualizá el `.env`.

## Decisiones que están esperándote

| Qué | Por qué importa |
|---|---|
| **¿Abrimos la app a más gente?** | Es la bifurcación grande. Todo lo que queda del plan (7 fases) necesita usuarios. Hasta que decidas, la app no sale de `127.0.0.1`. |
| **Si la abrimos: ¿Caddy o Tailscale?** | Si los que cargan son solo tu equipo, Tailscale deja **cero puertos abiertos a internet**. Caddy solo si un cliente tiene que entrar a ver el informe. |
| **¿Comentarios y adjuntos ahora?** | Andarían monousuario, pero sin autoría son notas sueltas y archivos sin dueño. Los dejé afuera por eso, no por imposibilidad. Si los querés igual, se hacen. |
| **El ejemplo de Word** | Quedaste en pasármelo para diseñar ese import. Sigue pendiente. |

## Lo que queda del plan (todo necesita usuarios)

- **Bloque A — la puerta de seguridad:** Fase 10 identidad · 11 autorización ·
  12 trabajo simultáneo · 13 exposición segura. **En ese orden y entero** antes de que
  la app salga de localhost.
- **Contenido:** Fase 20 comentarios con categoría y tags · 21 adjuntos.
- **Opcional:** Fase 25, link de solo lectura para que el cliente vea el informe sin
  cuenta.

Afuera del plan: el import desde Word y el asistente con IA que dejaste para después.

## Deudas técnicas conocidas

- ~~El repo no tiene tests con navegador~~ — **saldada** con la Fase 28:
  `tests/navegador/` cubre la barra de vista, el plegado, el scroll, las cabeceras y la
  vista persistida con clics reales. Lo que sigue sin test propio es el detalle fino del
  ancho de columnas en distintas resoluciones (verificado a mano en 1600px y 1366px).
- Las tres deudas de JS inline que la Fase 13 iba a tener que pagar para poner una CSP
  estricta **ya están saldadas** (todo vive en `static/grilla.js`, vendoreado).
