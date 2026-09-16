# 04 — Escala y dimensionado del caso de referencia

> **Aviso.** Este documento reemplaza por completo a su versión anterior, que dimensionaba un
> enjambre **disperso** (drones separados unos 158 m). Al fijarse una **separación máxima de 10 m
> entre drones**, el enjambre pasa a ser una **formación cohesionada** y casi todas aquellas
> conclusiones se invierten. Lo que sigue es el dimensionado correcto.

Decisiones de escala vigentes: **100 drones**, **10 km²**, **separación máxima de 10 m entre
drones**, **conocimiento solo de los vecinos**, **batería únicamente medida**.
Misión: **reconocimiento del terreno**.

**Los tres primeros son parámetros de configuración**, no constantes del programa. Los valores de
arriba son los del caso de referencia; el software debe admitir cualquier otro sin tocar código.

---

## 1. Parámetros configurables

| Parámetro | Símbolo | Valor de referencia | Rango previsto |
|---|---|---|---|
| Número de drones | `N` | 100 | 10 – 500 |
| Superficie de la zona | `A` | 10 km² | 0,01 – 100 km² |
| Separación máxima entre drones | `d_max` | 10 m | 2 – 500 m |
| Altura de vuelo | `h` | 5 m (ver §3) | 2 – 100 m |
| Forma de la formación | — | línea en ala | línea, rejilla `f × c`, cuña |
| Radio de comunicación | `R_com` | 150 m | 20 – 1.000 m |
| Velocidad de crucero | `v` | 15 m/s | 3 – 25 m/s |

---

## 2. Una ambigüedad que hay que resolver

"Máximo 10 metros entre uno y otro" admite dos lecturas, y la diferencia es de dos órdenes de
magnitud:

| | Lectura A — **separación al vecino** | Lectura B — **diámetro total** |
|---|---|---|
| Qué significa | Cada dron tiene algún vecino a ≤ 10 m: el enjambre es una **malla conectada** que puede ser muy ancha. | Los 100 drones caben dentro de una esfera de 10 m. |
| Geometría resultante | En línea: un frente de **990 m**. | 5,2 m³ por dron → separación real de **1,74 m**. |
| Ancho de barrido | Hasta 1 km | 20 m |
| Misión de 10 km² | **17 minutos** | **9,3 horas** |
| Sensatez | Los 100 drones aportan cobertura. | Los 100 drones miran casi el mismo punto: el enjambre se comporta como un solo sensor. |

**Se adopta la lectura A** como definición del caso de referencia, por ser la única que hace útil
un enjambre de 100 unidades para reconocer 10 km². La lectura B queda disponible sin más que
configurar una formación compacta, por si interesa como caso extremo.

> **Pendiente de confirmación del usuario.** Si lo que se quería era la lectura B, hay que
> replantear el tamaño del enjambre o el de la zona: 9,3 horas exceden con mucho cualquier
> autonomía real.

---

## 3. El hallazgo principal: la separación y la altura están acopladas

Con una cámara de 90° de apertura, la huella en el suelo mide **el doble de la altura de vuelo**.
Y si los drones van separados 10 m, esa huella determina cuánto se solapan:

| Altura | Huella | Redundancia con separación de 10 m |
|---:|---:|---:|
| **5 m** | **10 m** | **1,0× — cobertura exacta, sin huecos ni solape** |
| 10 m | 20 m | 4× |
| 20 m | 40 m | 16× |
| 50 m | 100 m | 100× |

A 50 m de altura, cada punto del terreno lo estarían mirando **cien drones a la vez**: el enjambre
haría cien veces el mismo trabajo. La separación de 10 m solo tiene sentido si se vuela **bajo**.

```
altura óptima = separación / 2      (para una cámara de 90°)
              = 10 / 2 = 5 metros
```

Esto reencuadra el proyecto entero, y para bien:

- Es una misión de **reconocimiento a baja cota**, no un vuelo de fotogrametría en altura.
- A 5 metros del suelo, el dron vuela **entre los obstáculos**, no por encima. La evitación de
  obstáculos deja de ser una precaución y pasa a ser el comportamiento que más trabaja.
- Con los drones a 10 m unos de otros y maniobrando entre obstáculos, la **anticolisión está
  activa permanentemente**.

> **Invierte el §2 de la versión anterior de este documento**, que concluía que la anticolisión
> apenas actuaría. Con formación cohesionada ocurre justo lo contrario: es el comportamiento
> dominante y el que marca los límites de todo lo demás.

---

## 4. La forma de la formación es la decisión de mayor impacto

El enjambre barre como una sola brocha, y el ancho de esa brocha depende de cómo se coloquen los
100 drones. A 5 m de altura y 15 m/s:

| Formación | Frente | Ancho de pasada | Pases | Barrido | Giros | **Total** |
|---|---:|---:|---:|---:|---:|---:|
| **Línea en ala (100 × 1)** | 990 m | 1.000 m | 4 | 14,1 min | 3,3 min | **17,4 min** |
| 50 × 2 | 490 m | 500 m | 7 | 24,6 min | 3,3 min | 27,9 min |
| 25 × 4 | 240 m | 250 m | 13 | 45,7 min | 3,3 min | 49,0 min |
| 10 × 10 (bloque) | 90 m | 100 m | 32 | 112,4 min | 3,4 min | 115,9 min |
| 4 × 25 (columna) | 30 m | 40 m | 80 | 281,1 min | 3,5 min | 284,6 min |

**De 17 minutos a 4 horas y 45 minutos, con los mismos 100 drones y la misma zona.** Un factor de
16 decidido únicamente por la geometría. Es, con diferencia, el parámetro más influyente del
proyecto, y **el experimento principal pasa a ser este**.

El resultado es intuitivo una vez visto: para barrer, lo que importa es el **frente**, y una línea
maximiza el frente por dron. Todo lo que no sea anchura es profundidad desaprovechada.

Lo que la tabla no dice, y el simulador sí dirá:

- Una línea de 1 km es **frágil**: más difícil de mantener, más lenta al girar, y basta un
  obstáculo para partirla.
- Una línea de 1 km **no cabe** en una calle urbana ni en un pasillo. En entorno urbano la
  formación tendrá que deformarse o dividirse, y ahí las formas compactas recuperan terreno.
- Con 4 pases, el ancho de pasada (1.000 m) y el lado de la zona (3.162 m) no encajan: el cuarto
  pase desperdicia un 26 % de su recorrido fuera de la zona. Ajustar el frente a un divisor del
  lado es una optimización barata.

### El giro, que no es gratis

Al final de cada pasada hay que dar la vuelta, y con un frente de 1 km eso no es un detalle:

| Maniobra | Coste |
|---|---:|
| **Rotar 180° sobre el centro** — el dron exterior recorre un semicírculo de 1.555 m | 104 s |
| **Giro en espejo** — nadie rota: cada dron invierte su rumbo y se desplaza lateralmente | **53 s** |

*(El giro en espejo resultó costar 52,7 s y no los 66 estimados aquí en un principio: el
desplazamiento lateral es el paso entre pasadas, 790 m, no el frente completo de 990 m, porque las
pasadas se reparten por igual sobre el lado de la zona.)*

El giro en espejo es más rápido y, sobre todo, **no exige que el dron exterior vuele a tope
mientras el interior casi se para**, que es el problema real de rotar una formación ancha. Como el
frente es simétrico, invertir el sentido de la marcha es equivalente a haber girado.

---

## 5. La cohesión de 10 m entra en la v1 (y no estaba prevista)

> **Cambia el documento 01, §3.** Allí se dejó explícitamente fuera de la primera versión el
> control de formaciones. La restricción de 10 m **es** control de formación, así que entra.

Mantener a 100 drones a ≤ 10 m unos de otros mientras esquivan obstáculos es un comportamiento por
derecho propio, y hay que implementarlo. Se hará como una fuerza más de las del documento 02, §4:
una **atracción hacia la posición que le corresponde al dron en la formación**, que compite con la
repulsión de los obstáculos y con la anticolisión.

### Y tiene que ser una restricción BLANDA

Este es el punto crítico, y lo demuestran los números del bosque:

| Densidad | Un árbol cada… | ¿Cabe una formación rígida de 10 m? |
|---:|---:|---|
| 200 árboles/ha | 7,1 m | **No** |
| 500 árboles/ha | 4,5 m | **No** |
| 1.000 árboles/ha | 3,2 m | **No** |

En un bosque real los huecos entre árboles son **más estrechos que la separación de la formación**.
Una formación rígida de 10 m sencillamente no puede atravesar un bosque: los drones tendrían que
volar a través de los troncos.

**Decisión: `d_max` se implementa como objetivo, no como candado.**

- Es una **fuerza de cohesión** que tira del dron hacia su sitio, no una atadura geométrica.
- Ante un obstáculo, la evitación **tiene prioridad**: el dron rompe formación, pasa, y vuelve.
- La separación real se **mide y se reporta** (media, máxima, y segundos fuera de tolerancia).
  Que la formación se deshaga y se rehaga es un resultado legítimo, y medir cuánto y cuándo es
  precisamente lo interesante.
- Existirá un modo estricto opcional que cuente cada violación como fallo, para quien quiera
  imponerla de verdad.

Esto convierte una limitación en uno de los mejores experimentos disponibles: **¿a qué densidad de
obstáculos se rompe una formación, y cuánto tarda en recomponerse?**

---

## 6. El reparto adaptativo de zonas ya no aplica como estaba pensado

> **Cambia el documento 01, §3.3.**

La estrategia Voronoi + Lloyd consistía en que cada dron se hiciera cargo de la porción de terreno
más cercana a él. Eso **exige que los drones se separen** para repartirse 10 km². Si están
obligados a permanecer a 10 m unos de otros, no pueden repartirse nada: sus regiones de Voronoi
serían parcelas de 10 × 10 m dentro de la propia formación.

Las dos estrategias de cobertura pasan a ser otras:

- **A — Formación única.** Los 100 drones como una sola brocha que recorre la zona en zigzag. Es
  la tabla del §4.
- **B — Enjambres divididos.** El enjambre se parte en `k` subenjambres cohesionados internamente
  (10 de 10, 4 de 25, 2 de 50…), y **el reparto Voronoi + Lloyd reaparece a nivel de subenjambre**:
  cada grupo se hace cargo de una región. Se recupera así toda la ventaja del reparto adaptativo
  —adaptación a zonas prioritarias, reconfiguración automática si un grupo falla— pero aplicada a
  grupos en lugar de a individuos.

La comparación A frente a B es el segundo experimento del proyecto. Nótese que B con `k = 1`
es A: la misma implementación cubre ambos casos, con `k` como parámetro.

---

## 7. El radio de comunicación cambia de papel

En la versión dispersa, `R_com` decidía si los drones podían coordinarse siquiera. Ahora, con
vecinos a 10 m, casi cualquier radio garantiza conectividad local. Pero aparece un efecto nuevo y
más sutil: **la información tarda en recorrer la formación**.

| `R_com` | Vecinos (en línea) | Saltos para cruzar el frente | Tiempo de propagación |
|---:|---:|---:|---:|
| 15 m | 2 | 99 | 4,95 s |
| 30 m | 6 | 33 | 1,65 s |
| 50 m | 10 | 20 | 1,00 s |
| 100 m | 20 | 10 | 0,50 s |

Un frente de 1 km con radio de 15 m tarda **casi 5 segundos** en que una orden llegue de un extremo
al otro. A 15 m/s, eso son 75 metros recorridos antes de que la formación entera reaccione: al
girar, un extremo empieza la maniobra cuando el otro todavía no se ha enterado, y la línea se
curva. Ese arrastre es un fenómeno real de los enjambres distribuidos, y el simulador lo
reproducirá solo, sin programarlo explícitamente, por el mero hecho de limitar quién habla con
quién.

El experimento se mantiene, reformulado: **¿cuánto deforma la formación el retardo de propagación,
y qué radio hace falta para que la línea gire limpia?**

### `R_com` tiene un mínimo que no es negociable

Hallazgo aparecido al implementar y probar la anticolisión, no previsto en el diseño sobre el
papel. Para que un dron pueda **ver venir** un cruce con el horizonte temporal que tiene
configurado, el radio de comunicación debe cubrir al menos lo que los dos drones recorren en ese
tiempo:

```
R_com  >=  velocidad de cierre máxima x horizonte
        =  2 x v_max x horizonte
        =  2 x 15 m/s x 4 s  =  120 metros
```

Con el valor de 30 m que figuraba en la tabla de arriba, dos drones que se acercan de frente a
15 m/s cada uno **se ven un segundo antes de chocar**, aunque el horizonte configurado diga cuatro.
No se obtiene un enjambre "más local": se obtiene una anticolisión que reacciona tarde, y sin
avisar de que lo hace.

**Decisión: `R_com` por defecto pasa a 150 m**, con margen sobre los 120 m mínimos. El programa
comprueba esta relación al validar la configuración y avisa si no se cumple, indicando cuál es el
horizonte efectivo real. Los valores pequeños de la tabla siguen siendo utilizables para estudiar
la degradación, pero ahora se sabe lo que se está midiendo.

---

## 8. El paso de integración se queda corto

Con drones a 10 m y velocidades de cierre de hasta 30 m/s:

| `dt` | Avance por paso | Acercamiento entre dos drones de frente | % de la separación |
|---:|---:|---:|---:|
| 0,05 s | 0,75 m | 1,50 m | **15 %** |
| **0,02 s** | 0,30 m | 0,60 m | **6 %** |
| 0,01 s | 0,15 m | 0,30 m | 3 % |

Consumir el 15 % de la separación en un solo paso es demasiado: la anticolisión reaccionaría a
saltos y aparecerían roces artificiales, provocados por el simulador y no por el algoritmo.

**Decisión: `dt = 0,02 s` (50 Hz) por defecto, configurable.** Multiplica por 2,5 el tiempo de
cálculo, que sigue siendo perfectamente asumible a 100 drones (§9).

> **Ajusta el documento 02, §1**, donde se fijó `dt = 0,05 s` razonando sobre obstáculos de varios
> metros. El criterio era correcto; lo que ha cambiado es que ahora la distancia crítica no es el
> tamaño del obstáculo, sino la separación entre drones.

---

## 9. Lo que no cambia

**Sigue sin hacer falta rejilla espacial a 100 drones.** Una matriz de distancias de 100 × 100 son
10.000 números que NumPy calcula de golpe. Que los drones estén juntos en lugar de dispersos no
altera el coste: la matriz es la misma.

> **Corregido con medidas.** Este documento situaba en unos 500 drones el umbral a partir del cual
> haría falta la rejilla. Medido con `unai banco`: 100 drones cuestan 3,2 ms por paso, 200 cuestan
> 15,7 y 400 cuestan 70,4. El coste es cuadrático con un extra por dejar de caber en caché, así que
> el umbral real está en torno a **250 drones**, no 500. Ver
> [`05-hallazgos-de-implementacion.md`](05-hallazgos-de-implementacion.md), §4.

**El tamaño del resultado sigue siendo cómodo.** Registro a 5 Hz con enteros de 16 bits:

| Duración | Fotogramas | Datos | Incrustado en HTML |
|---:|---:|---:|---:|
| 17 min | 5.100 | 3,1 MB | 4,1 MB |
| 20 min | 6.000 | 3,6 MB | 4,8 MB |
| 30 min | 9.000 | 5,4 MB | 7,2 MB |

**El bosque se almacena, no se genera al vuelo.** Un error aritmético de la versión anterior daba
5-10 millones de troncos para 10 km²; la cifra correcta es **0,5-1 millón** (10 km² son 1.000
hectáreas, a 500-1.000 árboles por hectárea). Un millón de troncos como `float32` ocupa 16 MB:
perfectamente almacenable. Se indexan en una **rejilla uniforme** construida una sola vez, con
tantas plazas por celda como exija la celda más poblada, de modo que la consulta "¿qué obstáculos
tengo cerca?" sea exacta y vectorizada. Se descarta la generación procedural, que era complejidad
innecesaria.

**La rejilla de cobertura baja a 5 m de celda**, no 10: la huella a 5 m de altura mide 10 m, y
medir con celdas del tamaño de la huella no detecta huecos. 5 m sobre 10 km² son 400.000 celdas,
0,8 MB. Asumible.

---

## 10. Lo que ya no vale de la versión anterior

| Afirmación anterior | Estado |
|---|---|
| Separación media de 158 m entre drones | **Anulada.** Ahora son 10 m por diseño. |
| La anticolisión apenas actúa en crucero | **Invertida.** Actúa permanentemente. |
| Hay que provocar congestión para probarla | **Innecesario.** La congestión es el estado normal. |
| El tránsito domina sobre el barrido | **Anulada.** Con un frente de 1 km, el barrido domina. |
| La posición de la base es parámetro clave | **Degradada.** Sigue contando, pero mucho menos. |
| `R_com` decide si el reparto adaptativo funciona | **Reformulada.** Ahora decide el retardo de propagación (§7). |
| Voronoi + Lloyd entre drones individuales | **Sustituida** por Voronoi entre subenjambres (§6). |
| Volar alto es rentable | **Invertida.** Volar alto multiplica la redundancia (§3). |
| Sin rejilla espacial; matriz densa | **Se mantiene.** |
| Bosque procedural por ser inviable almacenarlo | **Corregida.** Eran 0,5-1 millón de troncos, no 5-10 millones: sí caben en memoria (§9). |
| Interior a escala propia | **Se mantiene.** |

---

## 11. Resumen de decisiones nuevas

1. Se adopta la lectura A de la separación (malla conectada), pendiente de confirmación.
2. Altura por defecto **5 m**, derivada de la separación de 10 m y no elegida a mano.
3. La **forma de la formación** es el parámetro de mayor impacto y el experimento principal.
4. El giro se hace **en espejo**, no rotando.
5. La cohesión entra en la v1, implementada como **fuerza blanda** con prioridad a la evitación.
6. El reparto Voronoi sube de nivel: entre **subenjambres**, con `k` configurable.
7. `dt` baja a **0,02 s**.
8. La rejilla de cobertura baja a **5 m** de celda.
