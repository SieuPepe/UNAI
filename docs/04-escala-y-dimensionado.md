# 04 — Escala y dimensionado del caso de referencia

Documento derivado de las decisiones de escala tomadas: **100 drones**, **10 km²**,
**conocimiento solo de los drones cercanos**, **batería únicamente medida**.

Los números de aquí no son adorno: cambian decisiones concretas de implementación, y tres de
ellas corrigen o matizan lo escrito en los documentos 01 y 02. Van señaladas.

---

## 1. El caso de referencia

| Parámetro | Valor |
|---|---|
| Drones | 100 |
| Zona | 10 km² — un cuadrado de **3.162 × 3.162 m** |
| Superficie por dron | 100.000 m² (10 hectáreas) |
| Densidad | 10 drones por km² |
| Conocimiento | Solo vecinos dentro de un radio `R_com` |
| Batería | Se mide y se reporta; **no** condiciona la misión |

---

## 2. Primera consecuencia: es un enjambre MUY disperso

Con 100 drones repartidos por 10 km², la separación media entre un dron y su vecino más cercano
es de unos **158 metros**:

```
separación media ≈ 0,5 / raíz(densidad) = 0,5 / raíz(100/10.000.000) ≈ 158 m
```

Ciento cincuenta y ocho metros es *muchísimo* para drones que miden medio metro. Esto reordena
las prioridades del proyecto:

- **En crucero, la anticolisión casi no actúa.** Los drones sencillamente no se ven.
- **Las colisiones se concentran en tres sitios**: el despegue y la recogida en la base (donde
  están todos juntos), las **fronteras entre zonas** asignadas, y los **cuellos de botella** del
  entorno (una calle urbana, un pasillo del almacén).
- Por tanto, **los escenarios de prueba de la anticolisión deben provocar esos momentos** a
  propósito: despegue simultáneo, cruce de zonas, reasignación de un área tras un fallo. Un
  crucero tranquilo por campo abierto no prueba nada.

> **Matiza el documento 01, §3.2.** La anticolisión sigue siendo obligatoria, pero su banco de
> pruebas no es el vuelo normal, sino la congestión deliberada.

---

## 3. Segunda consecuencia: `R_com` pasa a ser el parámetro estrella

Al decidir que cada dron solo conoce a los cercanos, aparece un parámetro nuevo y central: el
**radio de comunicación / percepción `R_com`**. Con la densidad de este proyecto:

| `R_com` | Vecinos de media |
|---:|---:|
| 150 m | 0,7 |
| 300 m | 2,8 |
| 500 m | 7,9 |
| 800 m | 20,1 |
| 1.000 m | 31,4 |
| 1.500 m | 70,7 |

Con radio de 150 m, un dron vuela **solo**: no tiene con quién coordinarse. Con 1.500 m ve a casi
todo el enjambre y el sistema vuelve a ser, de hecho, centralizado. La zona interesante está en
medio.

### Por qué esto afecta directamente a la cobertura

Las dos estrategias de reparto del documento 01, §3.3 **no dependen igual de `R_com`**:

- **Barrido en franjas:** las zonas se asignan antes de despegar. Un dron no necesita hablar con
  nadie. Funciona con `R_com = 0`. A cambio, es rígido.
- **Reparto adaptativo (Voronoi + Lloyd):** un dron necesita conocer a los vecinos que delimitan
  su región para calcularla bien. Esos vecinos están, típicamente, a unas **dos o tres veces la
  separación media**, es decir entre 300 y 500 m. Con `R_com` por debajo de eso, el dron **cree
  que su región es más grande de lo que es**, se va hacia un centroide equivocado y aparecen
  solapes y huecos.

Esto convierte una decisión tuya en **el experimento más interesante del proyecto**:

> *¿A partir de qué radio de comunicación compensa el reparto adaptativo frente al barrido fijo?
> ¿Y a partir de qué radio deja de mejorar?*

Se espera encontrar un umbral en torno a los 400-600 m y una saturación más allá de los 800 m.
Ese es exactamente el tipo de respuesta que justifica construir este simulador.

> **Amplía el documento 03, §4.** Se añade a la lista de experimentos previstos.

---

## 4. Tercera consecuencia: el tránsito domina sobre el barrido

Cada dron recibe una zona de unos 316 × 316 m. Con una cámara de 90° de apertura, el ancho de
pasada es dos veces la altura de vuelo, y descontando un 20 % de solape:

| Altura | Ancho de pasada | Ancho útil | Camino a recorrer | Tiempo de barrido | Resolución |
|---:|---:|---:|---:|---:|---:|
| 20 m | 40 m | 32 m | 3.125 m | 208 s | 1,0 cm/píxel |
| 35 m | 70 m | 56 m | 1.786 m | 119 s | 1,8 cm/píxel |
| 50 m | 100 m | 80 m | 1.250 m | 83 s | 2,5 cm/píxel |
| 80 m | 160 m | 128 m | 781 m | 52 s | 4,0 cm/píxel |

(Tiempos a 15 m/s. Resolución estimada con un sensor de 4.000 píxeles de ancho.)

Ahora compárese con el **tránsito**: ir desde la base hasta la esquina opuesta de la zona son
4.472 m en diagonal, es decir **298 segundos**.

El resultado es contundente: **llegar a la zona cuesta más que barrerla.** A 50 m de altura, un
dron gasta 83 segundos trabajando y hasta 298 desplazándose.

Decisiones que se derivan de esto:

1. **La asignación de zonas debe minimizar el tránsito**, no solo repartir superficie: a cada dron
   la zona que le pilla más cerca. Un reparto que ignore esto puede duplicar el tiempo de misión
   sin cubrir un metro cuadrado más.
2. **La posición de la base es un parámetro de experimentación**, no un detalle. Base central
   frente a base en esquina frente a varias bases: el impacto es de minutos.
3. **Volar alto sale muy rentable en esta escala**, porque ahorra en la parte cara. Pero se paga
   en resolución y en exposición al viento (que a 80 m es notablemente más fuerte que a 20). Es
   justo el compromiso que el software debe cuantificar.
4. Misión completa estimada: **entre 6 y 10 minutos de vuelo**, holgadamente dentro de los 25-30
   minutos de autonomía de un multirrotor. **La escala elegida es viable.**

---

## 5. Cuarta consecuencia: no hace falta rejilla espacial

> **Corrige el documento 02, §12.**

El documento 02 explica que buscar vecinos comparando todos contra todos tiene coste cuadrático y
que la solución es una rejilla espacial. El principio es correcto, pero **a 100 drones la
conclusión práctica se invierte**:

```
100 drones  ->  matriz de distancias de 100 × 100 = 10.000 números por paso
mision de 15 min a 20 Hz = 18.000 pasos
total: 180 millones de operaciones -> NumPy lo resuelve en segundos
```

Una matriz de 100×100 ocupa 80 kilobytes y NumPy la calcula de una sola vez, sin bucles. Montar
una rejilla espacial en Python implicaría bucles a nivel de Python en cada paso, y **saldría más
lento** que la fuerza bruta vectorizada.

**Decisión: la v1 usa la matriz densa.** La rejilla espacial queda documentada como la ampliación
necesaria si algún día se pasa de ~500 drones, y no antes. Es un caso claro de no optimizar lo
que no duele.

*(La búsqueda de vecinos por `R_com` se hace sobre esa misma matriz: basta con enmascarar las
distancias mayores que el radio. Cero coste añadido.)*

---

## 6. El tamaño de los resultados

Una misión de 15 minutos con 100 drones son 1,8 millones de estados de dron. Guardarlos todos y
meterlos en un HTML de doble clic no es gratis:

| Frecuencia de registro | Fotogramas | `float32` | `int16` | Incrustado en HTML |
|---:|---:|---:|---:|---:|
| 20 Hz (todos) | 18.000 | 21,6 MB | 10,8 MB | 14,5 MB |
| 10 Hz | 9.000 | 10,8 MB | 5,4 MB | 7,2 MB |
| **5 Hz** | **4.500** | 5,4 MB | **2,7 MB** | **3,6 MB** |

**Decisión:**

- La **física se calcula a 20 Hz** (no se toca: es lo que da precisión).
- Las **trayectorias se registran a 5 Hz** y el visor **interpola** entre fotogramas. El ojo no
  distingue la diferencia; 5 fotogramas por segundo de vuelo simulado bastan de sobra para una
  reproducción suave, sobre todo pudiendo cambiar la velocidad de reproducción.
- Las posiciones se guardan como **enteros de 16 bits** referidos a los límites de la zona. Sobre
  3.162 metros, eso da una precisión de **4,8 centímetros**: muy por encima de lo que necesita un
  dibujo, y la mitad de tamaño que los decimales.
- Resultado: un visor autónomo de **unos 4 MB**, que abre sin problema con doble clic.
- Las **métricas sí se calculan a 20 Hz**, sobre todos los pasos. La distancia mínima entre drones
  no se puede muestrear: si se mira solo 5 veces por segundo, se puede pasar por alto justo el
  instante del roce.

---

## 7. La rejilla de cobertura

| Tamaño de celda | Celdas | Memoria |
|---:|---:|---:|
| 5 m | 400.000 | 0,80 MB |
| **10 m** | **100.000** | **0,20 MB** |
| 20 m | 25.000 | 0,05 MB |

**Decisión: 10 metros por defecto**, configurable. Es la décima parte del ancho de pasada a 50 m
de altura, lo bastante fino para detectar huecos reales y lo bastante grueso para no inflar el
fichero. Cada celda guarda el **instante** de la primera visita (no solo un sí/no), que es lo que
permite dibujar en el visor cómo se va "pintando" el mapa con el tiempo y calcular la curva de
cobertura del documento 03.

---

## 8. Cada entorno a su escala

**El caso de 10 km² no vale para los cuatro entornos.** Conviene decirlo claro antes de
programar: un almacén de 10 km² no existe.

| Entorno | Escala | Drones | Observaciones |
|---|---|---:|---|
| **Campo abierto** | 10 km² | 100 | El caso de referencia. |
| **Urbano** | 10 km² | 100 | ~1.000 manzanas de 100 m. Se almacenan explícitamente, sin problema. |
| **Bosque** | 10 km² | 100 | Ver aviso abajo. |
| **Interior / almacén** | 200 × 150 m (0,03 km²) | 10-20 | Escenario aparte, con sus propias métricas. Aquí sí hay congestión permanente, y es donde la anticolisión se pone realmente a prueba. |

### Aviso sobre el bosque

Un bosque real tiene entre 500 y 1.000 árboles por hectárea. En 10 km² eso son **entre 5 y 10
millones de troncos**. No se pueden guardar en una lista ni dibujar todos.

**Decisión: bosque procedural.** Los árboles no se almacenan: se *calculan* a demanda a partir de
las coordenadas de la celda y la semilla de la simulación. Preguntar "¿qué árboles hay cerca de
este dron?" devuelve siempre los mismos árboles para la misma semilla, sin haber guardado ninguno.
Memoria: cero. El visor dibuja únicamente los árboles próximos a la cámara.

---

## 9. La batería: se mide, no limita

Conforme a lo decidido, **no** habrá lógica de regreso a base por batería baja. La simulación
continúa aunque el consumo teórico supere la capacidad.

Pero sí se reporta, porque sigue siendo información útil para comparar configuraciones:

- Energía total y **energía por metro cuadrado cubierto** (la métrica de coste real).
- Batería restante del dron que peor acaba.
- **Marca de autonomía excedida**: si algún dron habría agotado la batería, se registra en qué
  segundo y qué porcentaje de misión quedaba pendiente en ese momento. La simulación no se
  detiene, pero el resultado queda etiquetado como *"no realizable con esta autonomía"*.

Así la configuración se puede comparar igual, sabiendo que sería inviable en la práctica.

---

## 10. Resumen de cambios sobre los documentos anteriores

| Documento | Cambio |
|---|---|
| 01, §3.2 | La anticolisión se prueba en congestión provocada, no en crucero. |
| 01, §8 | Las cuatro cuestiones abiertas quedan cerradas. |
| 02, §12 | A 100 drones **no** se usa rejilla espacial: matriz densa vectorizada. |
| 03, §4 | Nuevo experimento: umbral de `R_com` para que el reparto adaptativo compense. |
| — | Nuevo parámetro central del proyecto: `R_com`. |
| — | Nuevo parámetro de experimentación: la posición de la base. |
| — | El entorno interior corre a escala propia, con su propio caso de referencia. |
