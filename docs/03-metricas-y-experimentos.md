# 03 — Métricas y comparación de configuraciones

Uno de los dos objetivos del software es **decidir con números qué configuración es mejor**. Para
que eso signifique algo, hay que fijar de antemano qué se mide y cómo se comparan dos ejecuciones.
Este documento lo define.

---

## 1. Por qué esto se decide antes de programar

Si las métricas se añaden al final, salen las que resultan fáciles de calcular, no las que
importan. Y una métrica mal elegida lleva a conclusiones falsas con toda la apariencia de rigor.
Ejemplo: optimizar "cero colisiones" sin mirar nada más produce un enjambre perfecto que nunca
choca porque tampoco cumple la misión. Toda métrica de seguridad necesita al lado una métrica de
eficacia.

---

## 2. Qué se mide

### 2.1 Seguridad

| Métrica | Definición | Unidad |
|---|---|---|
| **Colisiones entre drones** | Veces que dos drones quedan a menos de su radio físico. | recuento |
| **Colisiones con el entorno** | Veces que un dron entra en un obstáculo o toca el suelo. | recuento |
| **Separación mínima** | La menor distancia entre dos drones en toda la misión. | metros |
| **Tiempo en riesgo** | Segundos acumulados con algún par de drones por debajo de la distancia de seguridad. | segundos |
| **Margen de seguridad** | Percentil 5 de la distancia al vecino más cercano. | metros |

Las colisiones son un recuento y deberían ser cero. Las otras cuatro son las que de verdad
discriminan: dicen *cuánto margen* hubo, no solo si hubo desastre. La **separación mínima** es
un único número, sensible a un caso aislado; el **margen de seguridad** (percentil 5) describe el
comportamiento habitual y es más robusto. Conviene mirar los dos.

### 2.2 Eficacia de la misión

| Métrica | Definición | Unidad |
|---|---|---|
| **Cobertura final** | Porcentaje de la zona visitada al acabar. | % |
| **Tiempo hasta el 90 %** | Segundos en cubrir el 90 % de la zona. | segundos |
| **Curva de cobertura** | Cobertura en función del tiempo (serie completa). | % vs s |
| **Huecos** | Celdas nunca visitadas, y si forman zonas contiguas. | recuento / m² |
| **Redundancia** | Veces que se visita una celda ya visitada. | media |

El **tiempo hasta el 90 %** suele ser más informativo que la cobertura final: casi todas las
estrategias llegan al 100 % si se les da tiempo infinito; la diferencia está en la velocidad. La
**redundancia** mide el trabajo desperdiciado por solapes.

### 2.3 Coste

| Métrica | Definición | Unidad |
|---|---|---|
| **Energía total** | Suma del consumo de todos los drones. | vatios-hora |
| **Energía por m² cubierto** | Coste unitario real de la misión. | Wh/m² |
| **Batería restante mínima** | El dron que peor acaba. | % |
| **Distancia recorrida** | Total y por dron. | metros |

La métrica que más dice es **Wh por metro cuadrado cubierto**: normaliza el coste por el trabajo
hecho y permite comparar configuraciones con distinto número de drones, que de otro modo no serían
comparables.

### 2.4 Calidad del comportamiento colectivo

| Métrica | Definición | Rango |
|---|---|---|
| **Dispersión** | Distancia media de cada dron al centro del enjambre. | metros |
| **Orden (polarización)** | Cuánto coinciden las direcciones de vuelo. | 0 a 1 |
| **Reparto de carga** | Desviación entre la superficie cubierta por cada dron. | % |
| **Tiempo bloqueado** | Segundos que los drones pasan atascados sin avanzar. | segundos |

La **polarización** se calcula promediando los vectores de dirección de todos los drones y midiendo
la longitud del resultado:

```
              │ 1        v_i  │
      phi  =  │ ─ · suma ──── │        phi = 1 → todos van al unísono
              │ N        |v_i|│        phi = 0 → direcciones desordenadas
```

El **tiempo bloqueado** es el detector directo del problema de los mínimos locales descrito en el
documento 02, §6. Si sube al cambiar de entorno, indica que hace falta un planificador de rutas.

---

## 3. Cómo se compara con honestidad

### 3.1 Una simulación no es un resultado

Cada ejecución lleva azar: la turbulencia, la colocación de los obstáculos, el ruido de posición.
Comparar la configuración A con la B ejecutando **una vez cada una** no demuestra nada: la
diferencia puede ser enteramente suerte.

**Regla del proyecto:** cada configuración se ejecuta con **N semillas distintas** (N ≥ 20 como
orientación) y se reportan la **mediana** y el **rango intercuartílico**, no un valor suelto. Una
configuración es mejor que otra cuando lo es de forma consistente a lo largo de las semillas.

### 3.2 Cambiar una cosa cada vez

Para saber qué causa una mejora, solo debe variar el factor estudiado. Todo lo demás —entorno,
número de drones, duración, y **el conjunto de semillas**— idéntico. Usar las mismas semillas en
A y en B es importante: enfrenta a las dos configuraciones exactamente al mismo viento y los
mismos obstáculos, lo que elimina buena parte del azar de la comparación.

### 3.3 No hay un único "mejor"

Seguridad y eficacia tiran en direcciones opuestas: separar más a los drones reduce el riesgo y
alarga la misión. No existe un ganador absoluto, existe una **frontera de compromisos**. La
herramienta de comparación dibujará esa frontera (cada configuración, un punto en el plano
seguridad-eficacia) y la decisión de qué punto conviene es humana, no del algoritmo.

---

## 4. Experimentos previstos

Los que justifican el software, en orden de interés:

1. **Barrido en franjas frente a reparto adaptativo Voronoi**, en los cuatro entornos. ¿Cuándo
   compensa la complejidad del segundo?
2. **Número de drones frente a tiempo de misión.** ¿Dónde está el punto en que añadir drones ya
   no acelera la misión porque se estorban entre ellos?
3. **Altura de vuelo.** Más altura cubre más por pasada pero gasta más y sufre más viento.
   ¿Cuál es la altura óptima en Wh/m²?
4. **Sensibilidad al viento.** ¿A partir de qué velocidad de viento la misión deja de ser viable?
5. **Distancia de seguridad y horizonte de anticolisión.** El compromiso directo entre prudencia
   y eficacia.
6. **Robustez ante fallos.** Si un dron cae a mitad de misión, ¿cuánto degrada cada estrategia?
   (Aquí el reparto adaptativo debería ganar con claridad.)
7. **Densidad del bosque.** ¿A qué densidad de obstáculos se rompe la evitación por campos
   potenciales?

---

## 5. Qué produce cada ejecución

- **Fichero de trayectorias**: la posición, velocidad y estado de cada dron en cada instante.
  Alimenta el visor y permite reanalizar sin volver a simular.
- **Resumen de métricas**: una línea con todos los indicadores de este documento, apta para
  apilar con las de otras ejecuciones en una tabla.
- **Visor**: fichero HTML autónomo con la reproducción interactiva.
- **Configuración usada**: copia exacta de los parámetros y la semilla, guardada junto al
  resultado. Sin esto, un resultado de hace tres meses es inservible.
