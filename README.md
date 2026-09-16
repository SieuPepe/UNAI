# UNAI — Simulador de enjambres de drones

Software para **simular el vuelo de un enjambre de drones en distintos entornos**, con dos
objetivos de uso:

1. **Comparar configuraciones.** Lanzar la misma misión variando parámetros (número de drones,
   distancia de seguridad, altura de vuelo, viento, algoritmo de reparto de zona) y obtener
   métricas numéricas que digan objetivamente qué configuración se comporta mejor.
2. **Ver cada simulación de forma interactiva.** Reproducir el vuelo en 3D en el navegador,
   orbitando la cámara, pausando, moviéndose por la línea de tiempo y activando capas de
   información (obstáculos, radios de seguridad, zona cubierta, vectores de velocidad).

> **Estado del proyecto: fase de diseño.** Todavía no hay código. Este repositorio contiene,
> por ahora, únicamente las definiciones y los fundamentos técnicos acordados.

## Arquitectura prevista

```
   ┌──────────────────────┐        ┌──────────────────┐        ┌─────────────────────┐
   │  Motor de simulación │  ───►  │  Fichero de      │  ───►  │  Visor 3D web       │
   │  Python + NumPy      │        │  trayectorias    │        │  HTML + Three.js    │
   │                      │        │  + métricas      │        │  (fichero único)    │
   │  calcula el vuelo    │        │                  │        │  reproduce el vuelo │
   └──────────────────────┘        └──────────────────┘        └─────────────────────┘
```

El motor y el visor están separados a propósito: el motor puede lanzar decenas de simulaciones
por lotes sin abrir ninguna ventana (para comparar), y el visor puede abrirse con doble clic sin
instalar nada ni necesitar servidor (para mirar).

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/01-decisiones-de-diseno.md`](docs/01-decisiones-de-diseno.md) | Qué se construye y qué no: modelo físico, comportamientos, entornos, alcance de la v1. |
| [`docs/02-fisica-y-matematicas.md`](docs/02-fisica-y-matematicas.md) | Explicación didáctica de la física y las matemáticas que ejecuta el simulador. |
| [`docs/03-metricas-y-experimentos.md`](docs/03-metricas-y-experimentos.md) | Qué mide el software y cómo se comparan dos configuraciones con rigor. |
| [`docs/04-escala-y-dimensionado.md`](docs/04-escala-y-dimensionado.md) | El caso de referencia (100 drones, 10 km²) y lo que esa escala impone al diseño. |

## Nombre

**UNAI** — *Unmanned Navigation & Autonomous Intelligence*.
