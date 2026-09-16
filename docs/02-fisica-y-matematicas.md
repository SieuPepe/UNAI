# 02 — La física y las matemáticas del simulador

Documento didáctico. Explica, sin dar por supuesto conocimiento previo, **qué calcula realmente
el programa** y por qué. Cada fórmula va acompañada de la explicación de qué significa cada
símbolo y de para qué sirve.

---

## 1. La idea central: el tiempo a rodajas

Un simulador no resuelve el vuelo "de una vez". Lo que hace es cortar el tiempo en rodajas muy
finas y, en cada rodaja, preguntarse una sola cosa:

> *"Dado dónde está cada dron y a qué velocidad va **ahora**, ¿dónde estará dentro de una
> centésima de segundo?"*

Repitiendo esa pregunta miles de veces, aparece el vuelo completo. A esa rodaja de tiempo la
llamamos **paso de integración**, `dt`.

```
dt = 0,05 segundos   →  20 pasos por cada segundo de vuelo simulado
```

Una misión de 5 minutos son 300 segundos × 20 = **6.000 pasos**. Si hay 100 drones, el programa
calcula 600.000 estados de dron. De ahí que importe que las operaciones sean eficientes.

**El compromiso del `dt`:** cuanto más pequeño, más fiel es el resultado, pero más lento va el
cálculo. Cuanto más grande, más rápido, pero aparecen errores: un dron puede "atravesar" una
pared fina porque en el paso anterior estaba delante y en el siguiente ya está detrás, sin haber
existido nunca dentro. Regla práctica: el dron no debe recorrer en un solo paso más de una
fracción del obstáculo más pequeño.

```
distancia recorrida en un paso = velocidad × dt = 15 m/s × 0,05 s = 0,75 metros
```

Con obstáculos de varios metros, 0,75 m por paso es seguro.

> **Ajuste para este proyecto.** La distancia crítica no acaba siendo el tamaño del obstáculo,
> sino la **separación entre drones**, que es de 10 m. Dos drones que se acercan de frente recortan
> 1,5 m por paso con `dt = 0,05`, un 15 % de su separación: demasiado, la anticolisión reaccionaría
> a saltos. **El valor por defecto pasa a `dt = 0,02 s` (50 Hz)**, donde el acercamiento es del 6 %.
> Ver [`04-escala-y-dimensionado.md`](04-escala-y-dimensionado.md), §8.

---

## 2. El estado de un dron: qué números lo describen

En el modelo cinemático que hemos elegido, un dron se describe en cada instante con dos vectores
de tres números cada uno:

```
posición   p = (x, y, z)      en metros
velocidad  v = (vx, vy, vz)   en metros por segundo
```

Un **vector** aquí no es más que una flecha: tiene dirección y longitud. La posición es la flecha
desde el origen del mapa hasta el dron; la velocidad es la flecha que indica hacia dónde y cómo
de rápido se mueve.

**Sistema de coordenadas elegido** (convención ENU, la habitual en robótica aérea):

```
x  →  hacia el Este
y  →  hacia el Norte
z  →  hacia ARRIBA          (z = 0 es el suelo; z = 30 son 30 metros de altura)
```

Dos operaciones con vectores que aparecen constantemente:

**Módulo** (la longitud de la flecha). Si la velocidad es (3, 4, 0):

```
|v| = raíz(vx² + vy² + vz²) = raíz(9 + 16 + 0) = 5 m/s
```

Es el teorema de Pitágoras en tres dimensiones. Sirve, por ejemplo, para saber si un dron supera
su velocidad máxima.

**Producto escalar** (mide cuánto "van en la misma dirección" dos flechas):

```
a · b = ax·bx + ay·by + az·bz
```

Si sale positivo, las dos flechas apuntan más o menos al mismo lado. Si sale negativo, en
sentidos opuestos. Si sale cero, son perpendiculares. Esta única operación es la que permitirá
al programa saber si un dron **se está acercando** a otro o alejándose de él (§7).

---

## 3. Cómo se avanza un paso: integración numérica

Sabemos la posición y la velocidad ahora. Queremos las de dentro de `dt`. La física de
bachillerato da la receta:

- La **aceleración** `a` es cuánto cambia la velocidad por segundo.
- La **velocidad** `v` es cuánto cambia la posición por segundo.

El programa usa el llamado **método de Euler semi-implícito**, que en la práctica son dos líneas:

```
v_nueva = v_actual + a · dt          ← primero se actualiza la velocidad
p_nueva = p_actual + v_nueva · dt    ← y la posición se mueve con la velocidad YA actualizada
```

**¿Por qué "primero la velocidad"?** Porque el orden importa. El método ingenuo (mover la
posición con la velocidad *vieja* y actualizar la velocidad después) tiene un defecto conocido:
en movimientos que dan vueltas u oscilan, va inyectando energía falsa en el sistema y el
resultado se va "hinchando" poco a poco hasta ser absurdo. Cambiando simplemente el orden, el
error deja de acumularse en una dirección y la simulación se mantiene estable durante horas de
vuelo simulado. Es la corrección más barata que existe en simulación: cero coste, mucha
estabilidad.

**Ejemplo numérico.** Dron parado en el origen que recibe una aceleración de 2 m/s² hacia el Este:

```
paso 1:  v = (0,0,0) + (2,0,0)·0,05 = (0,10 , 0, 0) m/s
         p = (0,0,0) + (0,10,0,0)·0,05 = (0,005 , 0, 0) m   → 5 milímetros

paso 2:  v = (0,10,0,0) + (2,0,0)·0,05 = (0,20 , 0, 0) m/s
         p = (0,005,0,0) + (0,20,0,0)·0,05 = (0,015 , 0, 0) m
```

Y así 6.000 veces.

---

## 4. De "quiero ir allí" a "cuánto acelero": el *steering*

Aquí está el corazón conceptual de todo simulador de enjambres, y es más sencillo de lo que
parece. El razonamiento, formulado originalmente por Craig Reynolds en 1987, es:

1. Un comportamiento (ir al destino, esquivar un árbol, separarse de un vecino) no ordena
   directamente "acelera tanto". Lo que produce es una **velocidad deseada**: *"a mí me gustaría
   ir a 10 m/s hacia allá"*.
2. La diferencia entre la velocidad que se desea y la que realmente se lleva es el **error**.
3. La aceleración que hay que aplicar es ese error repartido en un tiempo de reacción:

```
a = (v_deseada − v_actual) / tau
```

- `v_deseada`: la velocidad que el comportamiento pide.
- `v_actual`: la que el dron lleva ahora mismo.
- `tau` (tau): **tiempo de respuesta**, en segundos. Es el parámetro que define el "carácter" del
  dron. Con `tau = 0,2 s` el dron es nervioso y corrige bruscamente; con `tau = 1,5 s` es suave y
  perezoso. Es, en esencia, un controlador proporcional.

La belleza de este esquema es que **las aceleraciones se suman**. Cada comportamiento produce su
propia aceleración, con su propio peso de importancia, y el total es la suma:

```
a_total = w_meta·a_meta + w_obst·a_obstáculos + w_anti·a_anticolisión + w_sep·a_separación + a_viento
```

Los pesos `w` son los mandos que se pueden girar para cambiar la personalidad del enjambre:
subir `w_anti` produce drones muy prudentes que cumplen mal la misión; subir `w_meta` produce
drones eficientes que rozan el choque. **Encontrar el equilibrio entre esos pesos es exactamente
el tipo de comparación de configuraciones para el que se construye este software.**

---

## 5. Los límites físicos: saturación

Un dron real no puede acelerar infinitamente ni ir infinitamente rápido. Después de sumar todas
las aceleraciones, el programa **recorta** (satura) el resultado:

```
si |a_total| > a_max:     a_total = a_total · (a_max / |a_total|)
```

Esto conserva la **dirección** de la flecha pero reduce su **longitud** al máximo permitido. Es
importante recortar así y no truncar cada eje por separado: truncar por ejes deformaría la
dirección y el dron acabaría acelerando hacia donde no quería.

Lo mismo con la velocidad, distinguiendo horizontal de vertical, porque un multirrotor sube
mucho más despacio de lo que avanza:

```
|v_horizontal| ≤ v_max_h      (típico: 15 m/s)
 v_vertical    ∈ [−v_baja , v_sube]   (típico: entre −3 y +5 m/s)
```

**De dónde sale `a_max`.** No es un número inventado: procede de la relación empuje/peso del
aparato. Si los motores pueden empujar el doble de lo que pesa el dron (relación 2:1), le sobra
una fuerza equivalente a un peso para acelerar, y entonces:

```
a_max ≈ (relación_empuje_peso − 1) · g = (2 − 1) · 9,81 = 9,81 m/s²
```

donde `g = 9,81 m/s²` es la gravedad. Ese es el vínculo entre un dato de catálogo del dron y un
parámetro del simulador.

**Límite de giro.** Un dron tampoco cambia de rumbo al instante. El programa limita cuántos
radianes puede rotar el vector velocidad en un paso:

```
ángulo_max_por_paso = velocidad_de_giro_max · dt
```

---

## 6. Esquivar obstáculos: campos potenciales

### La intuición

Imagina el mapa como un paisaje de montañas y valles. En el destino hay un valle profundo; sobre
cada obstáculo hay una montaña puntiaguda. Sueltas una canica en la posición del dron: rueda
cuesta abajo hacia el destino y se aparta sola de las montañas. Eso es un **campo potencial**.

Matemáticamente, "rodar cuesta abajo" se llama seguir el **gradiente descendente**: el gradiente
es la flecha que apunta en la dirección de máxima subida, así que moverse en su contra es bajar.

### La atracción al destino

```
a_atracción = k_meta · (p_destino − p_dron) / |p_destino − p_dron|
```

`(p_destino − p_dron)` es la flecha que va del dron al destino. Dividirla por su propio módulo la
convierte en una flecha de longitud 1 (un **vector unitario**): conserva la dirección y olvida la
distancia. Multiplicada por `k_meta` da una atracción de fuerza constante, que se va frenando
cerca del destino para no pasarse de largo.

### La repulsión de los obstáculos

La fórmula clásica (Khatib, 1986) para un obstáculo que está a distancia `d`:

```
                 1        1     1  2
U_repulsión =  ─── · k · ( ─  −  ── )        ,  válido solo si d < d0
                 2         d     d0
```

Y la aceleración es la pendiente de ese paisaje:

```
a_repulsión = k · ( 1/d − 1/d0 ) · (1/d²) · û
```

- `d`: distancia del dron a la superficie del obstáculo, en metros.
- `d0`: **radio de influencia**. A más de `d0` metros, el obstáculo se ignora por completo. Es lo
  que evita que un edificio a 2 km siga empujando al dron.
- `û`: vector unitario que apunta del obstáculo hacia el dron (la dirección del empujón).
- `k`: la intensidad, un parámetro a ajustar.

Lo importante de la forma de esta fórmula es el término `1/d²`: **la repulsión crece
explosivamente al acercarse**. A 10 metros el obstáculo casi no se nota; a 1 metro empuja cien
veces más fuerte. Ese comportamiento es lo que garantiza que el dron nunca llegue a tocar.

### El problema conocido: los mínimos locales

Los campos potenciales tienen un fallo célebre. Si el dron se acerca de frente a una pared larga
y el destino está justo detrás, el empujón de la pared y la atracción del destino se cancelan
exactamente: el dron se queda **clavado**, sin fuerza neta, delante de la pared. Es un "mínimo
local": un valle que no es el valle bueno.

Tres remedios, que el simulador combinará:

1. **Componente tangencial (vórtice).** Además de empujar *hacia afuera*, el obstáculo empuja *de
   lado*, girando la flecha de repulsión 90°. El efecto es que el dron **rodea** el obstáculo en
   lugar de estrellarse contra él frontalmente.
2. **Ruido mínimo.** Una perturbación aleatoria pequeñísima rompe el equilibrio perfecto.
3. **Detección de bloqueo.** Si un dron lleva varios segundos sin avanzar hacia su meta, se le
   marca un destino intermedio lateral para que salga del atasco.

Merece la pena decirlo con franqueza: los campos potenciales son rápidos, locales y elegantes,
pero **no garantizan encontrar el camino**. Para entornos muy enrevesados (el almacén con
pasillos, por ejemplo) la solución correcta es añadir por encima un planificador de rutas de
verdad (A*, RRT), que sería la ampliación natural del proyecto.

---

## 7. No chocar entre drones: el punto de máxima aproximación

Esta es, matemáticamente, la parte más bonita del simulador, y es la que diferencia una
anticolisión ingenua de una buena.

### Por qué no basta con la distancia

Lo simple sería: *"si tengo un vecino a menos de 5 metros, me aparto"*. Pero eso reacciona tarde
y reacciona mal. Dos drones separados 4 metros que **vuelan en paralelo** no tienen ningún
problema; dos drones separados 40 metros que **vuelan de frente el uno contra el otro a 15 m/s**
chocan en poco más de un segundo. La distancia actual no informa del peligro: lo que informa es
**hacia dónde van**.

### El cálculo

Tomamos dos drones, `i` y `j`. Definimos la posición y la velocidad **relativas**:

```
r = p_j − p_i     ← flecha de mí hacia el otro (dónde está respecto a mí)
w = v_j − v_i     ← cómo se mueve el otro respecto a mí
```

Si ambos mantienen su velocidad, dentro de `t` segundos la distancia entre ellos será:

```
d(t) = | r + w·t |
```

Queremos saber **en qué momento esa distancia será la mínima**. Es un problema de mínimos.
Trabajamos con el cuadrado de la distancia, que es más cómodo y tiene el mínimo en el mismo sitio:

```
f(t) = |r + w·t|²  =  |r|²  +  2t (r · w)  +  t² |w|²
```

Derivamos respecto al tiempo e igualamos a cero:

```
f'(t) = 2 (r · w) + 2 t |w|² = 0
```

Y despejando se obtiene el resultado, que es una sola línea de código:

```
             − (r · w)
  t_cpa  =  ───────────
               |w|²
```

`t_cpa` es el **tiempo hasta el punto de máxima aproximación** (*closest point of approach*, de
donde vienen las siglas). Léelo así:

- **`t_cpa` negativo** → el momento de máxima cercanía ya pasó: se están **alejando**. No hay nada
  que hacer. (Aquí es donde el producto escalar `r · w` hace su trabajo: su signo dice si se
  acercan o se separan.)
- **`t_cpa` muy grande** → el cruce peligroso, si lo hay, está muy lejos en el futuro. Todavía no
  merece la pena maniobrar.
- **`t_cpa` pequeño y positivo** → atención.

Entonces se calcula a qué distancia pasarán en ese momento:

```
d_cpa = | r + w · t_cpa |
```

Y la regla de decisión es:

```
si  0 < t_cpa < horizonte_temporal   Y   d_cpa < distancia_de_seguridad :
        → maniobrar
```

- `horizonte_temporal`: cuántos segundos hacia el futuro mira el dron. Típico: 3 a 5 segundos.
  Es el parámetro "prudencia".
- `distancia_de_seguridad`: cuánto espacio quiere respetar. Típico: 3 a 5 metros.

### La maniobra

La corrección se aplica **perpendicular** a la trayectoria de aproximación, no hacia atrás.
Frenar es lento e ineficaz; desviarse de lado es rápido y no cuesta apenas avance. La intensidad
se gradúa con la urgencia: cuanto menor es `t_cpa`, más fuerte la corrección.

### Reciprocidad: la mitad cada uno

Detalle crucial. Si los dos drones se ven y cada uno hace la maniobra completa, se sobrecorrigen,
se cruzan, vuelven a verse y vuelven a corregir: aparece el **baile del pasillo**, esa oscilación
tan humana de dos personas que se esquivan a la vez hacia el mismo lado. La solución es que cada
dron asuma **la mitad** del esfuerzo, sabiendo que el otro hará la otra mitad, y que el lado de
la maniobra se decida con una regla fija e idéntica para ambos (por ejemplo, según el
identificador del dron, o siempre por la derecha, como en navegación marítima). Es el principio
del algoritmo **ORCA / velocidades recíprocas**, muy usado en robótica de enjambres.

---

## 8. El viento: cómo se simula algo que parece aleatorio pero no lo es

El viento es lo que separa una simulación de juguete de una creíble, y tiene un truco matemático
interesante.

### La velocidad respecto al suelo y respecto al aire

Un dron no se mueve "en el vacío": se mueve dentro de una masa de aire que a su vez se mueve.

```
v_suelo = v_aire + v_viento
```

- `v_suelo`: lo que ve un observador desde tierra (y lo que dibuja el visor).
- `v_aire`: la velocidad del dron **respecto al aire que lo rodea**, que es lo que producen sus
  motores y lo que limita su velocidad máxima.
- `v_viento`: la velocidad del aire en ese punto.

Consecuencia práctica muy real: un dron cuyo máximo es 15 m/s, volando contra un viento de
10 m/s, avanza sobre el terreno a solo 5 m/s. Y su batería se gasta como si fuera a 15. Esto el
simulador lo reproduce solo, sin ninguna regla especial, por el simple hecho de estar planteado
así.

### La turbulencia: ruido con memoria

Un error habitual de principiante es generar el viento con un número aleatorio nuevo en cada
paso. El resultado no se parece al viento: tiembla como una televisión sin señal, porque a 20
pasos por segundo la ráfaga cambia por completo 20 veces cada segundo.

El viento real **tiene memoria**: si ahora sopla fuerte, dentro de un segundo probablemente
seguirá soplando parecido. Eso se modela con un **proceso de Ornstein-Uhlenbeck** (también
llamado ruido de Gauss-Markov de primer orden), que suena intimidante y es una sola línea:

```
                    dt                     ┌──2·dt──┐
w_nuevo = w_actual·(1 − ──) + sigma · raíz │ ────── │ · N
                     T                     └───T────┘
```

- `w`: la ráfaga actual, en m/s.
- `T`: **tiempo de correlación**, en segundos. Es "cuánta memoria" tiene el viento. Con `T = 5 s`,
  las ráfagas duran unos segundos, que es lo realista. Es el parámetro que da el realismo.
- `sigma`: la intensidad de la turbulencia (desviación típica), en m/s.
- `N`: un número aleatorio de la campana de Gauss, con media 0 y desviación 1.

Leída en cristiano, la fórmula dice: **"parte de lo que había antes (primer término), y añádele
un empujón aleatorio pequeño (segundo término)"**. El primer término tira siempre hacia la calma;
el segundo desordena. El equilibrio entre ambos produce algo que, dibujado, se parece de verdad a
un anemómetro real. Es el mismo modelo que usan los simuladores de vuelo profesionales (la norma
militar MIL-F-8785C, modelo de Dryden, es una versión elaborada de esta idea).

### Variación con la altura

El viento no sopla igual a 2 metros del suelo que a 100: el rozamiento con el terreno lo frena
abajo. Se modela con la **ley de potencia**:

```
                     ┌  z  ┐ alfa
v_viento(z) = v_ref ·│ ─── │
                     └z_ref┘
```

Con `alfa` entre 0,1 (mar abierto, liso) y 0,4 (ciudad, muy rugoso). Es lo que hace que en el
entorno urbano volar bajo entre edificios proteja del viento, y que subir para esquivar tenga un
coste.

---

## 9. La resistencia del aire

Al moverse, el aire frena al dron. La fórmula física completa es:

```
F_resistencia = ½ · rho · Cd · A · |v_aire|²
```

- `rho`: densidad del aire, 1,225 kg/m³ a nivel del mar.
- `Cd`: coeficiente aerodinámico (para un dron, del orden de 1,0: son objetos muy poco
  aerodinámicos).
- `A`: área frontal que ofrece al viento, en m².
- El cuadrado de la velocidad: **doble de velocidad, cuádruple de resistencia**. Esta es la razón
  de que la autonomía caiga a plomo al volar rápido.

En el modelo simple, esta resistencia se absorbe dentro del parámetro `tau` del §4 (un dron que
no acelera se va frenando solo hasta quedarse quieto respecto al aire), lo cual es suficiente. La
fórmula completa queda anotada aquí para cuando se implemente el modelo de 6 grados de libertad.

---

## 10. Las misiones de cobertura: repartir un territorio

### Qué ve un dron: la huella del sensor

Una cámara apuntando hacia abajo, con un ángulo de apertura `theta`, volando a altura `h`, ve en
el suelo un círculo (o rectángulo) de radio:

```
                  theta
r_huella = h · tan(─────)
                     2
```

Ejemplo: cámara de 90° de apertura a 30 metros de altura → `r = 30 · tan(45°) = 30 metros`.
A 60 metros de altura, ve 60 metros de radio.

De aquí sale el **compromiso fundamental de toda misión de cobertura**: subir cubre más superficie
por pasada (el área crece con el *cuadrado* de la altura) pero con menos resolución por píxel,
más viento y más consumo. Es justo el tipo de decisión que este software está pensado para
resolver con números en lugar de con intuición.

### Medir la cobertura: la rejilla

La zona se divide en celdas cuadradas (por ejemplo de 5 × 5 metros). Cada celda guarda un dato:
visitada o no, y cuándo. En cada paso, el programa marca las celdas que caen dentro de la huella
de algún dron. La métrica es inmediata:

```
                  celdas visitadas
cobertura (%) = ──────────────────── × 100
                  celdas totales
```

Y se registra su evolución en el tiempo, que es la curva que de verdad permite comparar
estrategias: no interesa solo *si* se cubre el 100 %, sino **en cuánto tiempo se llega al 90 %**,
que suele ser la cifra operativamente relevante.

### Estrategia A: barrido en franjas (cortacésped)

La zona se parte en bandas de anchura igual a la huella del sensor, con un solape del 10-20 %
para no dejar huecos por errores de posición. Cada dron recorre las bandas que le tocan en
zigzag. Es exhaustivo, predecible y fácil de auditar. Es lo que se usa en agricultura de
precisión y fotogrametría. Su debilidad: es rígido, y si un dron falla, sus bandas quedan sin
cubrir.

### Estrategia B: reparto adaptativo (Voronoi + Lloyd)

Más elegante y es la referencia académica en control de cobertura (Cortés y Bullo, 2004).

**Partición de Voronoi:** cada punto del terreno pertenece al dron que lo tenga **más cerca**. El
territorio queda automáticamente troceado en polígonos, uno por dron, sin necesidad de que nadie
reparta nada: el reparto emerge de las posiciones.

**Algoritmo de Lloyd:** cada dron calcula el **centroide** (el centro de gravedad) de su propio
polígono y se mueve hacia él. Al moverse, los polígonos cambian, y se repite. Matemáticamente se
demuestra que este proceso converge: los drones acaban repartidos de forma óptimamente uniforme.

```
             Σ (posición del punto × importancia del punto)
centroide = ───────────────────────────────────────────────
                    Σ (importancia del punto)
```

La gracia del término "importancia" (la **función de densidad**) es que permite decir *"esta
esquina del polígono industrial importa el triple"* y los drones se concentrarán allí
automáticamente, sin cambiar ni una línea del algoritmo. Y si un dron cae, los polígonos de los
vecinos se expanden solos para cubrir su hueco: **la robustez es gratis**.

Comparar A y B en los cuatro entornos es, precisamente, uno de los experimentos que este
simulador debe permitir hacer.

---

## 11. La batería

Modelo simple pero fundamentado. La potencia consumida tiene dos partes:

```
P_total = P_sostenerse_en_el_aire + P_avanzar
```

La primera es la dominante y la más antiintuitiva: **un multirrotor gasta casi lo mismo parado en
el aire que avanzando**, porque la mayor parte de la energía se va en no caerse. De la teoría del
disco actuador:

```
                (m · g)^(3/2)
P_sostenerse = ───────────────
                raíz(2·rho·A)
```

- `m`: masa del dron (kg), `g`: gravedad, `rho`: densidad del aire, `A`: área total de los rotores.

La consecuencia de diseño es directa: **un dron detenido no ahorra**. En una misión de cobertura,
"esperar" cuesta casi lo mismo que "trabajar", así que las estrategias que dejan drones parados
son malas, y el simulador lo reflejará.

La energía se descuenta en cada paso y se contabiliza como porcentaje de batería:

```
E_restante(t+dt) = E_restante(t) − P_total · dt
```

---

## 12. El coste de calcular: por qué importa la informática

Para la anticolisión, cada dron debe mirar a sus vecinos. Si mira a **todos**:

```
número de parejas = N · (N − 1) / 2
```

- 10 drones → 45 parejas. Nada.
- 100 drones → 4.950 parejas. Por cada uno de los 6.000 pasos = **30 millones** de comprobaciones.
- 500 drones → 124.750 parejas → **750 millones**. Inviable.

Esto es lo que se llama coste **cuadrático**: multiplicar los drones por 10 multiplica el trabajo
por 100.

**La solución: rejilla espacial.** Se divide el espacio en cubos del tamaño del radio de
interacción. Cada dron se apunta en el cubo donde está. Para buscar vecinos, basta con mirar su
cubo y los 26 adyacentes, e ignorar el resto del mundo. Como un dron solo tiene unos pocos
vecinos cerca por muy grande que sea el enjambre, el coste pasa de cuadrático a **lineal**:
multiplicar los drones por 10 multiplica el trabajo por 10, no por 100.

Es el mismo principio que usa un mapa por cuadrículas: para buscar un restaurante cercano no
recorres la guía entera, miras tu cuadrícula.

### Pero ojo: a 100 drones, la fuerza bruta gana

El razonamiento anterior explica el **principio**, y es correcto. La conclusión práctica para este
proyecto, sin embargo, es la contraria, y conviene saberlo antes de escribir código.

Con 100 drones, la tabla de todas las distancias entre todos es una matriz de 100 × 100 = 10.000
números, que ocupa 80 kilobytes y que NumPy calcula **de una sola vez, sin bucles**. Montar una
rejilla espacial en Python obligaría a recorrer cubos y listas en cada uno de los 18.000 pasos, y
saldría **más lento** que la fuerza bruta vectorizada.

La lección general vale más que el caso concreto: *el algoritmo asintóticamente mejor no siempre
es el más rápido en la escala real del problema*. La rejilla espacial es la respuesta correcta a
partir de unos 500 drones. Por debajo, es complejidad que no paga. Ver
[`04-escala-y-dimensionado.md`](04-escala-y-dimensionado.md), §5.

---

## 13. El ciclo completo, paso a paso

Lo que ejecutará el programa **20 veces por cada segundo de vuelo simulado**:

```
 1. Reconstruir la rejilla espacial con las posiciones actuales.          (§12)

 2. Para cada dron, buscar sus vecinos cercanos.                          (§12)

 3. Calcular la aceleración de cada comportamiento:
      · atracción hacia su objetivo de misión                             (§4, §10)
      · repulsión + rodeo de obstáculos del entorno                       (§6)
      · anticolisión predictiva con vecinos (punto de máxima aproximación)(§7)
      · separación mínima de cortesía entre vecinos                       (§7)

 4. Sumar las aceleraciones con sus pesos.                                (§4)

 5. Recortar la aceleración total al máximo físico del dron.              (§5)

 6. Actualizar la velocidad:  v = v + a·dt                                (§3)
      y recortarla a la velocidad máxima y al giro máximo.                (§5)

 7. Añadir el viento del punto donde está el dron.                        (§8)

 8. Actualizar la posición:   p = p + v·dt                                (§3)

 9. Descontar la batería consumida.                                       (§11)

10. Marcar en la rejilla de cobertura las celdas que el dron acaba de ver.(§10)

11. Registrar métricas del instante: distancia mínima entre drones,
    colisiones, cobertura acumulada, energía.                             (doc 03)

12. Guardar el estado para el visor y volver al paso 1.
```

---

## 14. Glosario rápido

| Término | Qué significa aquí |
|---|---|
| **Vector** | Una flecha con dirección y longitud: posición, velocidad o aceleración. |
| **Módulo** | La longitud de esa flecha. Pitágoras en 3D. |
| **Producto escalar** | Operación que dice si dos flechas apuntan al mismo lado. Su signo revela si dos drones se acercan o se alejan. |
| **Integración** | Avanzar la simulación un pasito en el tiempo. |
| **`dt`** | La duración de ese pasito. Aquí, 0,05 segundos. |
| **Steering** | Convertir "quiero ir allí" en "acelero así". |
| **Saturación** | Recortar un valor a su máximo físico conservando la dirección. |
| **Campo potencial** | Paisaje imaginario de montañas (obstáculos) y valles (destinos) por el que el dron "rueda". |
| **Gradiente** | La pendiente de ese paisaje. Moverse en su contra es bajar. |
| **Mínimo local** | Un valle que no es el bueno: el dron se queda atascado ahí. |
| **CPA** | *Closest Point of Approach*: el instante futuro de máxima cercanía entre dos drones. |
| **Ornstein-Uhlenbeck** | Ruido aleatorio con memoria. Lo que hace que el viento parezca viento. |
| **Voronoi** | Reparto de un territorio asignando cada punto al dron más cercano. |
| **Centroide** | El centro de gravedad de una región. |
| **Coste cuadrático** | Que al doblar los drones, el trabajo se multiplica por cuatro. |
| **Semilla** | El número que fija el azar para que una simulación se pueda repetir idéntica. |

---

## 15. Para profundizar

- **Craig Reynolds (1987)**, *Flocks, Herds and Schools* — el origen del modelo de steering (§4).
- **Oussama Khatib (1986)**, *Real-Time Obstacle Avoidance* — los campos potenciales (§6).
- **van den Berg, Guy, Lin, Manocha (2011)**, *Reciprocal n-body Collision Avoidance* (ORCA) — la
  anticolisión recíproca (§7).
- **Cortés, Martínez, Karatas, Bullo (2004)**, *Coverage Control for Mobile Sensing Networks* — el
  reparto Voronoi-Lloyd (§10).
