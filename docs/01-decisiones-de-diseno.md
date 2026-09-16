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

### 3.3 Misiones de cobertura
El enjambre barre una zona: reparto del área entre los drones, recorrido eficiente y registro de
qué porcentaje queda cubierto y en cuánto tiempo. Se implementarán dos estrategias, para poder
compararlas entre sí:

- **Barrido en franjas** (tipo cortacésped): la zona se parte en bandas y cada dron recorre las
  suyas en zigzag. Predecible y exhaustivo.
- **Reparto adaptativo por regiones** (Voronoi + Lloyd): cada dron se hace cargo de la porción de
  terreno más cercana a él y se va recolocando. Se adapta solo si un dron cae o si la zona tiene
  partes más importantes que otras.

### Fuera de la v1 (pero previsto)
Flocking (bandada emergente) y formaciones geométricas. No se descartan: el sistema de
comportamientos será una lista de "fuerzas" combinables, así que añadirlos después es agregar
piezas, no rediseñar.

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

## 8. Cuestiones ABIERTAS

| # | Cuestión | Por qué importa |
|---|---|---|
| A1 | ¿Cuántos drones como máximo debe aguantar con soltura? (¿30, 100, 500?) | Determina si hace falta optimizar la búsqueda de vecinos desde el principio. |
| A2 | ¿Tamaño típico de la zona a cubrir? (¿una manzana, un polígono industrial, varios km²?) | Afecta a la escala, la autonomía necesaria y el tamaño de los ficheros de resultado. |
| A3 | ¿Los drones conocen la posición de todos los demás, o solo de los cercanos? | Es la diferencia entre un enjambre "centralizado" y uno realmente distribuido. |
| A4 | ¿Se modela la batería como limitación real de la misión (con regreso a base) o solo se mide? | Cambia si la misión puede fracasar por autonomía. |
