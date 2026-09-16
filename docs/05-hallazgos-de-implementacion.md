# 05 — Hallazgos de implementación

Lo que se descubrió al programar y probar, y que el diseño sobre el papel no había previsto. Se
recoge aquí porque varios de estos puntos son correcciones de los documentos 01 a 04, y porque la
mayoría no son errores de código sino **de razonamiento**: el código hacía exactamente lo que
estaba escrito, y lo escrito estaba mal pensado.

---

## 1. Cuatro fallos que solo aparecen al ejecutar

### 1.1 El guiado sin anticipación deja a la formación permanentemente rezagada

**Síntoma.** El error medio al puesto se estabilizaba en **8,79 m** y el guía de la ruta frenaba al
71 % de su velocidad. La misión habría durado un 40 % más de lo debido.

**Causa.** La ley de seguimiento del documento 02, §4 es proporcional al error de posición:

```
v_deseada = ganancia × (puesto − posición)
```

Un dron solo acelera si **ya** va retrasado. En cuanto el puesto se mueve a velocidad constante, se
alcanza un equilibrio con error permanente: el error es precisamente lo que genera la velocidad
necesaria para seguir el ritmo. Nunca desaparece.

**Corrección.** Añadir el término anticipativo: la velocidad del propio puesto.

```
v_deseada = velocidad_del_puesto + ganancia × (puesto − posición)
```

Ahora el error tiende a cero porque la velocidad de crucero ya no hay que "ganársela".

**Efecto medido:** error de 8,787 m a **0,213 m**; avance de la ruta del 4,2 % al **11,9 %** en los
mismos 120 segundos, frente a un 12,0 % ideal.

> Corrige el documento 02, §4, donde la ley de guiado se presentaba sin este término.

### 1.2 La medición de cobertura sobrestimaba la superficie un 59 %

**Síntoma.** Un dron cuya cámara ve 78,54 m² marcaba 125 m² de terreno. Y la dispersión entre
mediciones era **exactamente cero**, lo que delató el problema: un estimador correcto tendría que
variar según dónde cayera el dron dentro de su celda.

**Causa.** La plantilla de celdas cubiertas estaba construida en **índices de celda**: se marcaban
siempre las mismas posiciones relativas a la celda que ocupaba el dron, independientemente de su
posición real dentro de ella. El número de celdas marcadas era, por tanto, una constante.

**Corrección.** Decidir la pertenencia midiendo la distancia real del dron al **centro de cada
celda candidata**.

**Efecto medido:** sesgo del +59,2 % a **−0,0 %** con celdas de 2,5 m. El tamaño de celda por
defecto baja de 5 m a 2,5 m, porque con celdas del tamaño del radio de la huella el sesgo residual
sigue siendo del −3,7 %.

### 1.3 El desempate del término tangencial valía cero justo donde hacía falta

**Síntoma.** Un dron lanzado contra un árbol **lo atravesaba**, con desvío lateral exactamente 0,00
metros. Subir la intensidad de la repulsión por diez no cambiaba nada.

**Causa.** El documento 02, §6 identifica correctamente el problema de los mínimos locales y receta
la componente tangencial: empujar de lado además de hacia afuera, para que el dron rodee. La
implementación elegía el lado con el signo de la proyección de la velocidad sobre la tangente:

```
sentido = signo(tangente · velocidad)
```

En una aproximación **perfectamente frontal** esa proyección vale cero, y por tanto el término
tangencial también. El remedio se desactivaba solo en el único caso para el que existía.

**Corrección.** Romper el empate con un lado fijo, que es la regla de navegación marítima: dos
barcos que se cruzan de frente caen ambos a estribor.

**Efecto medido:** de atravesar el tronco a dejar **7,4 m de margen**.

### 1.4 Faltaba el límite de velocidad de acercamiento

Es el hallazgo de más calado, y aplica por igual a los obstáculos y a los pares de drones.

**Síntoma.** Tras corregir el punto anterior, un dron seguía estrellándose contra una pared larga.
La traza mostró por qué: llegaba a **1,88 m de la pared con 6,7 m/s hacia ella**.

**Causa.** Frenar 6,7 m/s en 1,88 m exige

```
a = v² / (2d) = 44,9 / 3,76 = 11,9 m/s²
```

y el aparato solo tiene 9,81. **En ese punto ya no existe maniobra posible**, por buena que sea la
lógica de esquive. El dron había gastado su presupuesto de aceleración en apartarse de lado en
lugar de en no llegar tan rápido.

Detrás hay un defecto de forma del campo potencial. El término 1/d² vale, con los parámetros del
proyecto:

| Distancia | Aceleración repulsiva |
|---:|---:|
| 17 m | 0,009 m/s² |
| 10 m | 0,06 m/s² |
| 1 m | 285 m/s² |

Es decir: **nada de lejos y una pared de ladrillo de cerca**. Un dron a 15 m/s recorre 17 metros en
poco más de un segundo; cuando el campo empieza a notarse, ya está encima.

**Corrección, en dos partes.**

1. **Esquive predictivo por tiempo hasta el impacto**, con la misma lógica que la anticolisión
   entre drones: se mide a qué velocidad se acerca el dron a la superficie y cuánto tardaría en
   alcanzarla; si falta menos que el horizonte, se aplica aceleración lateral creciente con la
   urgencia. El campo potencial queda como barrera de última defensa, no como mecanismo principal.

2. **Límite de velocidad de acercamiento por distancia de frenado**, la regla del conductor:

   ```
   velocidad_permitida = raíz( 2 × a_freno × (distancia − margen) )
   ```

   Si la velocidad de acercamiento la supera, se frena con contundencia. Esto es lo que hace la
   evitación **físicamente realizable**: garantiza que nunca se llegue a un estado del que no se
   pueda salir. Se aplica igual a los pares de drones, donde la deceleración disponible es el doble
   porque frenan los dos a la vez.

**Efecto medido** sobre el enjambre de 100 drones en 90 segundos:

| Escenario | Colisiones con el entorno | Colisiones entre drones |
|---|---:|---:|
| Bosque 200 árboles/ha | 1.425 → **4** | 77 → **2** |
| Bosque 500 árboles/ha | 19 → **14** | 194 → **6** |
| Urbano | 0 → **0** | 274 → **8** |

Y en los casos aislados: un dron contra un árbol de frente deja 7,4 m; contra una pared de 80 m,
1,6 m y la rodea; dos drones de frente se cruzan con 4,4 m.

> Amplía el documento 02, §6 y §7. El campo potencial puro no basta a velocidad de crucero; hace
> falta predicción y, sobre todo, la condición de frenado.

### 1.5 La tangencia de las huellas es una cobertura de cuchillo

**Síntoma.** La misión de referencia completa, con cero colisiones y la formación perfecta,
terminaba con **95,52 % de cobertura** en vez del 100 %.

**Diagnóstico.** El mapa de huecos los situó confinados a `y ∈ [1.685, 2.265] m`: exactamente la
franja que barría **una sola** de las cuatro pasadas, aquella donde ninguna pasada vecina solapaba.
Ni un hueco en el resto de la zona.

La causa es aritmética. Con drones cada 10 m y huella de radio 5 m, las huellas quedan
**tangentes**: se tocan en un punto. En la pasada en cuestión, las trayectorias caían sobre 1,25 m
módulo 2,5, es decir justo sobre los centros de las celdas de medición. La fila de celdas
intermedia entre dos drones quedaba entonces a **5,00 metros exactos** de ambos, o sea en el borde
mismo de las dos huellas, y nunca se marcaba: una de cada cuatro filas de celdas de esa pasada.

Forzando esa alineación a propósito en un caso aislado, la cobertura cae al **72,5 %** frente al
95 % de una fase cualquiera.

**Corrección.** El documento 02, §10 ya prescribía un solape del 10-20 % entre pasadas contiguas
"para no dejar huecos por errores de posición". Lo que faltaba era aplicar el mismo criterio
**entre drones**. La altura de vuelo derivada pasa a incluirlo:

```
altura = (separación / 2) × (1 + solape) = 5,00 × 1,15 = 5,75 m
```

Huella de 11,5 m, redundancia de 1,32. Con solape cero se recupera la tangencia, por si interesa
estudiarla.

**Lección de fondo, más allá del número.** El error no estaba en el código, que hacía exactamente
lo prescrito; estaba en tratar una condición geométrica de borde —"las huellas se tocan"— como si
fuera una condición de cobertura. Un borde tiene grosor cero, y nada real cae exactamente sobre él
de forma fiable. Un diseño que depende de una igualdad exacta no es un diseño ajustado: es un
diseño que aún no ha fallado.

---

## 2. El radio de comunicación tiene un mínimo no negociable

Para que la anticolisión **vea venir** un cruce con el horizonte que tiene configurado:

```
R_com  ≥  2 × v_max × horizonte  =  2 × 15 × 4  =  120 metros
```

Con los 30 m que figuraban en el diseño, dos drones que se acercan de frente a 15 m/s cada uno se
ven **un segundo antes de chocar**, aunque el horizonte configurado diga cuatro. No se obtiene un
enjambre más local: se obtiene una anticolisión que reacciona tarde y no avisa de ello.

El valor por defecto pasa a **150 m** y la validación comprueba la relación, indicando cuál sería el
horizonte efectivo real.

---

## 3. El giro tomado en seco cuesta 16 metros de error

El guía de la ruta doblaba la esquina a velocidad de crucero. El enjambre no puede: revertir 15 m/s
con 9,81 m/s² cuesta `v²/2a` = **11,5 metros** como mínimo físico. El error de formación pasaba de
0,01 m en tramo recto a **16,16 m** en cada vértice.

No era un fallo de control —esa parte es física— pero sí lo era que el guía ignorase el problema.
Aplicando por tercera vez el principio de distancia de frenado, ahora el guía **decelera antes de
la esquina**. El pico baja a **10,42 m** y el error mediano en crucero se queda en 0,00 m.

---

## 4. El coste crece con el cuadrado del enjambre, y antes de lo previsto

Medido con `python -m unai banco` en CPU:

| Drones | ms por paso | Misión completa |
|---:|---:|---:|
| 25 | 0,42 | 21 s |
| 50 | 1,09 | 55 s |
| 100 | 3,22 | 2,7 min |
| 200 | 15,73 | 13 min |
| 400 | 70,37 | 59 min |

De 100 a 200 drones el coste se multiplica por 4,9, y de 200 a 400 por 4,5: cuadrático, con un
extra por dejar de caber en la caché del procesador.

> **Matiza el documento 04, §9**, que situaba en unos 500 drones el punto a partir del cual haría
> falta rejilla espacial. Con las medidas en la mano, la matriz densa es cómoda hasta unos **150-200
> drones**; a 400 ya duele. El umbral real está en torno a 250, no a 500.

---

## 5. La GPU: implementada, medida y desaconsejada a esta escala

La casilla existe y funciona, con aviso visible y continuación en CPU si no hay GPU utilizable.
Pero el pronóstico del documento 01, §5.1 se mantiene: a 100 drones las matrices son de 100 filas,
y cada operación cuesta del orden de 5-10 microsegundos en despacharse al chip, se opere sobre cien
números o sobre diez millones. Un paso encadena decenas de operaciones.

**No se ha podido medir en hardware real**: el equipo de desarrollo no tiene GPU. `unai banco` está
preparado para medir el punto de cruce en cuanto haya una, y hasta entonces lo honrado es decir que
la ruta de GPU está escrita y probada solo contra la ruta de CPU, no verificada sobre silicio.

Para que la semilla produzca el mismo escenario en ambos dispositivos, **todo el azar se sortea en
la CPU** y se transfiere. Dos ejecuciones en el mismo dispositivo son idénticas; entre dispositivos
son equivalentes pero no bit a bit, porque la GPU acumula las sumas en otro orden.

---

## 6. Correcciones menores

- **El bosque de 10 km² son 0,5-1 millón de troncos, no 5-10 millones.** Diez km² son 1.000
  hectáreas, a 500-1.000 árboles por hectárea. Sí caben en memoria (16 MB), así que se almacenan e
  indexan en una rejilla en vez de generarse al vuelo. Se descarta la generación procedural, que
  era complejidad innecesaria.
- **El giro en espejo cuesta 52,7 s, no 66 s.** El desplazamiento lateral es el paso entre pasadas
  (790 m), no el frente completo de la formación (990 m), porque las pasadas se reparten por igual
  sobre el lado de la zona.
- **El paso de integración de 0,02 s queda confirmado.** La distancia crítica no es el tamaño del
  obstáculo sino la separación entre drones.
- **La cuantización a 16 bits da 4,82 cm de error máximo** sobre 3.162 m, exactamente lo previsto.
  Una misión de 17 minutos son 3,1 MB, también lo previsto.

---

## 7. Limitaciones conocidas

Cosas que el simulador hace mal o no hace, dichas sin adornos.

- **Los campos potenciales siguen sin garantizar camino.** En un callejón sin salida el dron se
  queda atascado —no choca, pero no sale—. Es la trampa descrita en el documento 02, §6, y por eso
  se mide el tiempo bloqueado. La solución de fondo es un planificador de rutas (A*, RRT) por
  encima, y no está hecha.
- **El entorno urbano no es practicable para un frente de 1 km a 5 m de altura.** En las pruebas el
  enjambre pasa la mitad del tiempo bloqueado y cubre una fracción mínima. El resultado es correcto
  y es un hallazgo, no un error: una línea de un kilómetro no cabe en una calle de veinte metros.
  Hace falta que la formación se divida, y eso es la estrategia B del documento 01, §3.4, todavía
  sin implementar (`k_subenjambres` existe en la configuración pero aún no reparte).
- **La batería solo se mide**, conforme a lo decidido: no provoca regreso a base.
- **El terreno es plano.** No hay relieve.
- **No hay fallos de drones** ni pérdida de comunicación: el experimento de robustez del documento
  03, §4 necesita la máscara de drones activos, prevista pero no implementada.
- **La ventana de lanzamiento no se ha podido ejecutar** en el equipo de desarrollo, que no tiene
  Tkinter instalado. Su lógica —traducir los campos a una configuración— sí está probada, pero el
  dibujo de la ventana no.
