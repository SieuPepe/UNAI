# 01 — Decisiones de diseño

Documento de referencia con las condiciones acordadas antes de empezar a programar.
Todo lo que aparece aquí como **CERRADO** es una decisión tomada; lo marcado como **ABIERTO**
está pendiente de decidir y no bloquea el arranque.

---

## 1. Objetivo del software

Dos usos, ambos de primera categoría:

- **Comparar configuraciones.** Ejecución por lotes, reproducible y sin interfaz gráfica, que
  produce métricas numéricas para decidir qué configuración es mejor.
- **Inspeccionar una simulación concreta de forma interactiva.** Visor 3D en el navegador.

Esta doble finalidad es la razón de separar motor y visor.

### Qué significa "interactivo" aquí — CERRADO

El visor es de **reproducción interactiva**, no de simulación en vivo. Es decir:

- **Sí:** orbitar/acercar la cámara, pausar y reanudar, cambiar la velocidad de reproducción,
  arrastrar la barra de tiempo hacia adelante y atrás, seleccionar un dron y seguirlo, activar
  y desactivar capas (obstáculos, radios de seguridad, estelas, mapa de cobertura, vectores de
  velocidad), leer las métricas del instante mostrado.
- **No (por ahora):** mover un dron con el ratón durante el vuelo o cambiar el viento en caliente
  y ver el efecto al instante. Eso exige que el cálculo corra dentro del navegador y queda como
  posible modo "en vivo" futuro (ver §7).

La justificación: el cálculo en Python es el que da repetibilidad y métricas fiables, que es el
objetivo principal. Reproducir un resultado ya calculado permite exactamente el mismo grado de
exploración visual, pero sobre datos que se pueden auditar y comparar.

---

## 2. Modelo físico del dron — CERRADO

**Modelo cinemático con límites físicos**, diseñado desde el principio para poder sustituirse por
un modelo más complejo sin reescribir el resto.

Cada dron se representa como un punto con masa que tiene:

- Posición y velocidad en 3D.
- Velocidad máxima (horizontal y vertical, con valores distintos).
- Aceleración máxima (equivale al límite de empuje de los motores).
- Velocidad de giro máxima (un dron no cambia de rumbo instantáneamente).
- Resistencia del aire, de forma simplificada.
- Batería con un consumo que depende de lo que esté haciendo.

**No** se simulan: los cuatro rotores por separado, la inclinación del aparato, los giroscopios,
ni los controladores internos de vuelo.

### Preparado para crecer

La arquitectura definirá una **interfaz común de "modelo de vuelo"**: el resto del simulador
(comportamientos, entornos, métricas, visor) solo sabe pedir *"dron, intenta ir a esta velocidad
durante este intervalo"* y leer dónde ha acabado. Cambiar el modelo cinemático por un
cuadricóptero completo de 6 grados de libertad será sustituir esa pieza, sin tocar nada más.

Motivo de empezar simple: con el modelo cinemático caben cientos de drones a velocidad cómoda,
que es lo que hace falta para estudiar *comportamiento de enjambre*. El modelo completo aporta
realismo de *un* aparato, y es lo que interesa más tarde, cuando el comportamiento ya funcione.

---

## 3. Comportamientos del enjambre — CERRADO

Entran en la primera versión:

### 3.1 Evitación de obstáculos
El dron esquiva edificios, árboles, paredes y terreno. Basado en **campos potenciales**: los
obstáculos "empujan" al dron y el destino lo "atrae". Se complementa con una componente
tangencial para bordear el obstáculo en lugar de quedarse bloqueado de frente.

### 3.2 Anticolisión entre drones
Los drones no chocan entre sí. Basado en **tiempo hasta la máxima aproximación**: en lugar de
reaccionar solo a la distancia actual, cada dron predice si su trayectoria y la de su vecino se
van a cruzar peligrosamente y corrige antes. La maniobra es **recíproca**: si los dos drones se
ven, cada uno hace la mitad del esfuerzo, lo que evita el efecto "baile" de dos personas que se
esquivan mutuamente en un pasillo.

Con la separación máxima de 10 m fijada para el enjambre, este comportamiento **está activo de
forma permanente**, no solo en momentos de congestión. Es el que marca los límites de todo lo
demás. Ver [`04-escala-y-dimensionado.md`](04-escala-y-dimensionado.md), §3.

### 3.3 Cohesión de la formación

El enjambre vuela junto: cada dron mantiene una separación máxima `d_max` (10 m en el caso de
referencia) respecto a sus vecinos. Se implementa como **fuerza blanda** —una atracción hacia el
puesto que le toca en la formación— y **no** como atadura geométrica, porque en un bosque los
huecos entre árboles son más estrechos que la propia formación y una formación rígida
sencillamente no cabe. Ante un obstáculo, la evitación tiene prioridad: el dron rompe formación,
pasa y se reincorpora. Cuánto se deshace y cuánto tarda en recomponerse es una métrica, no un
fallo.

La **forma de la formación** (línea en ala, rejilla de `f × c`, cuña) es configurable y resulta ser
el parámetro de mayor impacto de todo el proyecto: decide el ancho de barrido y, con él, el tiempo
de misión.

### 3.4 Misiones de cobertura

El enjambre barre una zona en reconocimiento a baja cota y se registra qué porcentaje queda
cubierto y en cuánto tiempo. Dos estrategias comparables entre sí:

- **A — Formación única.** Los 100 drones como una sola brocha que recorre la zona en zigzag. El
  ancho de la brocha lo da la forma de la formación.
- **B — Enjambres divididos.** El enjambre se parte en `k` subenjambres, y el reparto adaptativo
  **Voronoi + Lloyd** opera entre grupos: cada subenjambre se hace cargo de la región que le queda
  más cerca y se recoloca solo si otro falla o si hay zonas prioritarias.

Con `k = 1`, B es A: la misma implementación cubre ambas, con `k` como parámetro.

> El reparto Voronoi **entre drones individuales**, previsto en la versión inicial de este
> documento, queda descartado: exigía que los drones se separasen para repartirse el terreno, lo
> que es incompatible con mantenerlos a 10 m. Ver
> [`04-escala-y-dimensionado.md`](04-escala-y-dimensionado.md), §6.

### Fuera de la v1 (pero previsto)

Flocking de bandada emergente al estilo Reynolds, como alternativa a la formación con puestos
asignados. El sistema de comportamientos es una lista de fuerzas combinables, así que añadirlo es
agregar una pieza, no rediseñar.

---

## 4. Entornos — CERRADO: los cuatro

Todos comparten la misma representación interna (una lista de obstáculos geométricos + un campo
de viento + límites del espacio aéreo), de modo que el mismo enjambre y la misma misión puedan
lanzarse en cualquiera de ellos y compararse.

| Entorno | Contenido | Qué pone a prueba |
|---|---|---|
| **Campo abierto** | Suelo plano o con relieve suave. Viento configurable: componente constante + ráfagas + turbulencia. | El comportamiento base del enjambre y su resistencia a perturbaciones. |
| **Urbano** | Bloques de edificios de distintas alturas, calles entre ellos, altura mínima y máxima de vuelo permitidas. | Navegación por "cañones", drones que se pierden de vista entre sí, rodeos. |
| **Bosque** | Obstáculos cilíndricos (troncos) distribuidos aleatoriamente con densidad configurable, a baja altura. | Evitación de obstáculos a alta frecuencia, muchos obstáculos cercanos a la vez. |
| **Interior / almacén** | Recinto cerrado con paredes, pasillos, estanterías y techo. | Espacios estrechos, ausencia de GPS (más ruido de posición), imposibilidad de "subir para esquivar". |

Cada entorno se define en un fichero de configuración legible, con semilla aleatoria, para que
"bosque denso semilla 42" sea siempre exactamente el mismo bosque.

---

## 5. Stack técnico — CERRADO

| Pieza | Tecnología | Motivo |
|---|---|---|
| Motor de simulación | Python 3 + NumPy | Cálculo vectorizado: los N drones se actualizan en una operación, no en un bucle. |
| Configuración | Ficheros de texto (YAML/JSON) | Un experimento es un fichero; se versiona en Git y se comparte. |
| Resultados | Fichero de trayectorias + métricas | Auditable y reutilizable sin volver a simular. |
| Visor | HTML + Three.js, fichero único | Se abre con doble clic: sin servidor, sin instalación, sin internet. |
| Análisis comparativo | Python (tablas + gráficas) | Comparar decenas de ejecuciones de una tacada. |

**Requisito para el usuario:** tener Python 3 instalado. El visor no requiere nada.

---

## 5.1 Interfaz de lanzamiento — CERRADO

Además de la línea de órdenes, el software tiene una **ventana de lanzamiento** desde la que se
introducen los parámetros a mano antes de simular. Se construye con Tkinter, que viene incluido
en la instalación estándar de Python en Windows, así que no añade ninguna dependencia.

Controles obligatorios:

| Control | Tipo | Parámetro |
|---|---|---|
| **Número de drones** | campo numérico | `n_drones` |
| **Distancia máxima entre drones** | campo numérico | `separacion_max_m` |
| **Usar GPU** | **casilla de verificación** | `usar_gpu` |

Y, por comodidad, también: entorno, forma de la formación, lado de la zona, duración, semilla y
altura de vuelo (que por defecto se calcula sola a partir de la separación, §5.2 del documento 04).

La ventana muestra en vivo las magnitudes derivadas —frente de barrido, altura sin solape, número
de pasadas y tiempo estimado de misión— de modo que se vea el efecto de cada cambio **antes** de
lanzar, que es donde está el valor: la diferencia entre una formación en línea y una en columna
son minutos frente a horas, y conviene saberlo antes de esperar.

La línea de órdenes se mantiene como interfaz principal para el uso por lotes: comparar
configuraciones exige lanzar decenas de simulaciones sin abrir ninguna ventana (`docs/03`, §3.1).
La ventana escribe exactamente la misma configuración que consume la línea de órdenes, así que un
lanzamiento manual es reproducible después sin la ventana.

### Dispositivo de cálculo — CERRADO

El motor corre indistintamente en **CPU (NumPy)** o en **GPU de NVIDIA (CuPy)**, seleccionable con
la casilla. Conviene decir sin rodeos lo que cabe esperar: **a 100 drones la GPU será más lenta que
la CPU.** Cada operación sobre matrices cuesta del orden de 5-10 microsegundos en despacharse al
chip, se opere sobre cien números o sobre diez millones, y un paso de simulación encadena decenas
de operaciones sobre matrices de 100 filas. La GPU empieza a compensar a partir de varios miles de
drones. Se implementa igualmente porque el enjambre es un parámetro libre y porque el punto de
cruce se mide, no se supone: el proyecto incluye un banco de pruebas que lo determina en cada
máquina.

Si se marca la casilla y no hay GPU utilizable, se **avisa de forma visible** y se continúa en CPU.
Un respaldo silencioso haría que una comparación de rendimiento mintiera sin que nadie se enterase.

---

## 6. Principios de construcción — CERRADO

1. **Reproducibilidad total.** Toda aleatoriedad (viento, colocación de obstáculos, ruido de
   sensores) depende de una semilla declarada. Misma configuración + misma semilla = resultado
   idéntico, bit a bit. Sin esto, comparar configuraciones no significa nada.
2. **Unidades del Sistema Internacional** en todo el código: metros, segundos, kilogramos,
   radianes. Las conversiones a km/h o grados se hacen solo al mostrar.
3. **Separación estricta** entre: modelo de vuelo · comportamientos · entorno · métricas · visor.
   Cada uno se puede sustituir sin tocar los demás.
4. **Verificable automáticamente.** Comprobaciones que se ejecutan solas: ningún dron supera su
   velocidad máxima, ningún dron atraviesa un obstáculo, la energía consumida nunca es negativa.
5. **Configuración sin tocar código.** Cambiar el número de drones o la fuerza del viento es
   editar un fichero de texto o pasar un argumento, nunca modificar el programa.

---

## 7. Ampliaciones previstas (no en la v1)

Se enumeran para que las decisiones de hoy no las bloqueen:

- Modelo dinámico de cuadricóptero de 6 grados de libertad.
- Modo "en vivo": simulación dentro del navegador para trastear con parámetros en caliente.
- Flocking y formaciones geométricas.
- Fallos y averías: pérdida de un dron, pérdida de comunicación, deriva de sensores.
- Comunicación con alcance limitado entre drones (hasta ahora se asume información compartida).
- Sensores simulados con campo de visión y oclusión real.
- Terreno con relieve real importado de mapas de elevación.

---

## 8. Escala del caso de referencia — CERRADO

Las cuatro cuestiones que quedaban abiertas han sido resueltas:

| # | Cuestión | Decisión |
|---|---|---|
| A1 | Tamaño del enjambre | **100 drones.** |
| A2 | Zona a cubrir | **10 km²** (un cuadrado de 3.162 × 3.162 m). |
| A3 | Conocimiento del enjambre | **Solo los vecinos cercanos**, dentro de un radio de comunicación `R_com`. Enjambre genuinamente distribuido. |
| A4 | Batería | **Solo se mide.** No provoca regreso a base ni aborta la misión; se reporta el consumo y se marca la misión como no realizable si se excede la autonomía. |

Estas cifras tienen consecuencias de calado sobre el resto del diseño —entre otras, que el
enjambre resulta muy disperso, que el tránsito pesa más que el barrido, y que a 100 drones no
conviene usar rejilla espacial—. Todo ello está analizado y cuantificado en
[`04-escala-y-dimensionado.md`](04-escala-y-dimensionado.md), **de lectura obligada antes de
implementar**.

A ello se añade una restricción posterior que reordena el diseño: **los drones vuelan a una
separación máxima de 10 m entre sí**, de modo que el enjambre es una formación cohesionada y no un
conjunto disperso. `N`, `A` y `d_max` son **parámetros de configuración**; los valores citados son
los del caso de referencia.

Parámetros centrales del proyecto, por orden de influencia:

- **La forma de la formación.** Decide el ancho de barrido y con él el tiempo de misión: entre 17
  minutos y casi 5 horas para la misma zona y los mismos 100 drones.
- **`d_max`**, la separación máxima entre drones (10 m).
- **La altura de vuelo**, que no se elige libremente: queda acoplada a `d_max` por la huella de la
  cámara. Con 10 m de separación, la altura coherente es de 5 m.
- **`R_com`**, el radio de comunicación, que ahora determina cuánto tarda una orden en recorrer la
  formación de un extremo al otro.
- **La posición de la base**, de influencia menor con un frente de barrido ancho.
