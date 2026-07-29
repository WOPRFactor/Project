# Para retomar

Nota corta para abrir mañana y saber dónde estamos. El detalle está en
`PLAN-DE-OBRA.md` (v1) y `PLAN-DE-MEJORAS.md` (v2); esto es solo el punto de entrada.

## Levantar la app

En PowerShell, desde la carpeta del proyecto (acordate: `;` y no `&&`):

```powershell
git pull
uv sync
uv run uvicorn app.main:app --reload
```

Después, `http://127.0.0.1:8000`.

## Dónde quedó

Todo lo que funciona con un solo usuario está hecho: **444 tests en verde**. El ciclo
cierra de punta a punta — cargás o importás, planificás, congelás lo aprobado, medís
el desvío y emitís el informe.

Lo último de la sesión fueron tres arreglos del Gantt, encadenados: la grilla había
crecido tanto que tapaba el timeline; al arreglarlo se cortaron los títulos; al
arreglar eso aparecieron dos barras de scroll. Los tres cerrados y medidos en el
navegador.

## Lo que marcó Ariel para mañana

**1. Se pierden los nombres de las columnas al bajar** (bug). El encabezado de la
grilla se va con el scroll vertical. Falta `position: sticky` en la cabecera, en las
dos mitades — la de la grilla y la del timeline (meses y semanas), o al bajar tampoco
se sabe qué semana es cada barra.

**2. Riesgos: revisar la sección más a fondo** (a definir con Ariel). Hoy tiene
registro, cuadrante 5×5 y el tilde en la grilla. Falta charlar qué le falta: puede ser
el plan de respuesta (evitar / mitigar / transferir / aceptar), riesgo residual
—probabilidad e impacto *después* de mitigar, que es lo que se reporta—, disparadores,
fecha de revisión, o vincular el riesgo a una tarea de mitigación del cronograma.
**No arrancar sin definirlo con él.**

**3. No se pueden prender columnas desde el selector** (bug mío, ya diagnosticado).
El `hx-vals` de `#mirada-actual` —que existe para que la vista sobreviva a cada
edición— **pisa** los checkboxes del formulario: el request sale con el conjunto viejo
y la columna nueva nunca llega. Reproducido en el navegador: al tildar «Peso» se envía
`columnas=avance,dias,fin,inicio,pred,resp`, sin `peso`.
*Arreglo:* sacar `columnas` del `hx-vals` heredado y que el formulario de vista lo
mande solo, o mover ese formulario fuera del contenedor con `hx-vals`. Es chico.
*Por qué se me pasó:* verifiqué el filtro por URL (`?columnas=...`), que ejercita el
servidor pero saltea el control. **El test que falta es el que toca el checkbox.**

**4. Poder apagar las flechas de dependencias** (pedido). Van como un control más de
la mirada, al lado de Detalle / Etapa / Color, viajando en la URL igual que el resto.
Chico: las flechas ya se calculan aparte en `vista._flechas`.

## Lo primero que conviene mirar

1. **Abrí tu proyecto y mirá el Gantt.** Es lo que estuvimos arreglando y no lo viste
   funcionando todavía.
2. **Probá el selector de Columnas** (arriba de la grilla, dice «Columnas (6 de 13)»)
   y **arrastrá el borde de la columna Tarea**. Los anchos se guardan por proyecto.
3. **Decidí las columnas por defecto.** Hoy vienen Resp., Predec., Días, Inicio, Fin y
   Avance. Con esas, en 1600px al título le quedan ~295px y se corta en 33 de tus 41
   tareas. Si me decís cuáles usás de verdad, achico el default y el título se
   ensancha solo. Es cambiar una línea.

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

- El ancho de las columnas es CSS y **no lo cubre ningún test**: se verificó a mano en
  el navegador, en 1600px y en 1366px. Blindarlo pediría tests con navegador, que hoy
  el repo no tiene.
- Las tres deudas de JS inline que la Fase 13 iba a tener que pagar para poner una CSP
  estricta **ya están saldadas** (todo vive en `static/grilla.js`, vendoreado).
