# UNAI — Simulador de enjambres de drones

Simula el vuelo de un **enjambre de drones en formación cohesionada** que reconoce el terreno a
baja cota, en cuatro entornos distintos, con dos finalidades:

1. **Comparar configuraciones.** Ejecutar la misma misión variando parámetros y obtener métricas
   numéricas que digan objetivamente qué configuración se comporta mejor.
2. **Ver cada simulación de forma interactiva.** Reproducir el vuelo en 3D en el navegador,
   orbitando la cámara, recorriendo la línea de tiempo y activando capas de información.

**Caso de referencia:** 100 drones separados un máximo de 10 m entre sí, reconociendo 10 km² a
5,75 metros de altura. Los tres parámetros son configurables.

---

## Instalación

Hace falta Python 3.10 o posterior.

```powershell
git clone -b claude/determined-darwin-fumkh2 https://github.com/SieuPepe/UNAI.git "$HOME\UNAI"; cd "$HOME\UNAI"; pip install numpy; python -m unai ventana
```

`numpy` es la única dependencia obligatoria. Opcionales: `pyyaml` para configuraciones en YAML y
`cupy-cuda12x` para calcular en GPU.

---

## Uso

### Ventana de lanzamiento

```powershell
python -m unai ventana
```

Se introducen el **número de drones**, la **distancia máxima entre drones** y se marca la
**casilla de GPU**, además del entorno, la formación y el resto de parámetros. La ventana calcula
en vivo el frente de barrido, la altura sin solape, las pasadas y la duración estimada, de modo
que se ve el efecto de cada cambio antes de lanzar. Al terminar abre el visor.

Tkinter viene con Python en Windows y macOS; en Linux se instala aparte (`sudo apt install
python3-tk`).

### Línea de órdenes

```powershell
python -m unai estimar --drones 100 --separacion 10 --entorno bosque
python -m unai simular --config configs/referencia.json --abrir
python -m unai simular --drones 200 --separacion 6 --formacion linea --km2 4 --viento 8 --gpu
python -m unai lote --config configs/bosque.json --semillas 20
python -m unai banco --drones-lista 50,100,500,2000
```

- `estimar` muestra las magnitudes derivadas sin simular nada.
- `simular` ejecuta una misión y escribe `visor.html`, `metricas.json`, `serie.csv` y `config.json`.
- `lote` repite con varias semillas y resume mediana y cuartiles, que es como se compara con
  rigor: una sola ejecución de cada configuración no demuestra nada.
- `banco` mide CPU frente a GPU y busca el punto de cruce en la máquina concreta.

### Escenarios incluidos

| Fichero | Qué es |
|---|---|
| `configs/referencia.json` | 100 drones en línea sobre 10 km² de campo abierto. |
| `configs/campo-viento.json` | Lo mismo con viento de 8 m/s y ráfagas. |
| `configs/bosque.json` | 500 árboles por hectárea: la formación no cabe y se rompe. |
| `configs/urbano.json` | Manzanas de 80 m con calles de 20 m. |
| `configs/interior.json` | Almacén de 200 × 150 m con 15 drones, a escala propia. |
| `configs/bloque-10x10.json` | La misma misión en bloque en vez de en línea. |

---

## El visor

Un único fichero HTML que se abre con doble clic: sin servidor, sin instalación, sin internet y
sin librerías externas —el 3D se proyecta a mano sobre un lienzo 2D—. Pesa unos 4 MB para una
misión completa.

- Arrastrar para orbitar, rueda para acercar, Mayús+arrastrar para desplazar.
- Espacio pausa, las flechas avanzan paso a paso, la barra recorre el tiempo.
- Doble clic sobre un dron para seguirlo.
- Capas: mapa de cobertura, obstáculos, estelas, radios de seguridad y vectores de velocidad.

---

## Lo que ya se sabe

Resultados que salieron al construirlo y que condicionan cómo usarlo.

**La forma de la formación decide el tiempo de misión.** Con los mismos 100 drones sobre la misma
zona: en línea, 17 minutos; en bloque de 10 × 10, casi dos horas. Para barrer solo cuenta el
frente, y la profundidad es anchura desaprovechada.

**La altura de vuelo no es libre: la fija la separación.** La huella de una cámara de 90° mide el
doble de la altura, así que con drones a 10 m las huellas se tocan a 5 m de altura. Pero tocarse no
basta: sin solape, la cobertura real se quedó en el 95,5 %, y con las trayectorias mal alineadas
llega a caer al 72,5 %. Se vuela un 15 % más alto, a 5,75 m. A 50 m de altura, en cambio, cada
punto lo mirarían cien drones a la vez.

**El radio de comunicación tiene un mínimo.** Para que la anticolisión vea venir un cruce con el
horizonte que tiene configurado hacen falta `2 × v_max × horizonte` = 120 m. Con menos, no se
obtiene un enjambre más local: se obtiene una anticolisión que reacciona tarde.

**Una formación rígida no atraviesa un bosque.** Con 500 árboles por hectárea hay un tronco cada
4,5 m y los drones van a 10 m. La separación máxima se implementa como fuerza blanda, no como
atadura: el dron rompe formación, pasa y vuelve. Que se deshaga es un resultado, no un fallo.

**La GPU no acelera a esta escala.** Medido: 100 drones son matrices de 100 filas, y cada
operación cuesta más en despacharse al chip que en resolverse. La casilla está y funciona, pero la
GPU compensa a partir de varios miles de drones.

**El coste crece con el cuadrado del enjambre.** Medido en CPU: 25 drones 0,42 ms por paso, 100
drones 3,2 ms, 400 drones 70 ms. Una misión completa de 100 drones son unos 3 minutos de cálculo.

---

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/01-decisiones-de-diseno.md`](docs/01-decisiones-de-diseno.md) | Qué se construye y qué no. |
| [`docs/02-fisica-y-matematicas.md`](docs/02-fisica-y-matematicas.md) | Explicación didáctica de la física y las matemáticas del simulador. |
| [`docs/03-metricas-y-experimentos.md`](docs/03-metricas-y-experimentos.md) | Qué se mide y cómo se comparan dos configuraciones. |
| [`docs/04-escala-y-dimensionado.md`](docs/04-escala-y-dimensionado.md) | El caso de referencia y lo que esa escala impone. |
| [`docs/05-hallazgos-de-implementacion.md`](docs/05-hallazgos-de-implementacion.md) | Lo que se descubrió al programar y probar, y que no estaba en el diseño. |

---

## Estructura

```
unai/
  config.py           parámetros, validación y ficheros de configuración
  calculo.py          selección de dispositivo: CPU (NumPy) o GPU (CuPy)
  entorno.py          los cuatro entornos y la rejilla de obstáculos
  viento.py           viento medio con perfil de altura y turbulencia con memoria
  vuelo.py            modelo de vuelo, sustituible por un 6-DOF
  formacion.py        línea, rejilla y cuña; giro en espejo
  comportamientos.py  puesto, evitación, anticolisión, separación y cohesión
  cobertura.py        ruta de barrido y mapa de lo reconocido
  metricas.py         los indicadores con que se compara
  registro.py         trayectorias cuantizadas a 16 bits
  simulacion.py       el bucle principal
  estimacion.py       magnitudes derivadas, antes de simular
  visor.py            generación del visor autónomo
  interfaz.py         ventana de lanzamiento
  banco.py            medición de CPU frente a GPU
  cli.py              línea de órdenes
tests/                57 comprobaciones automáticas
configs/              escenarios de referencia
```

Ejecutar las comprobaciones: `python -m pytest tests/ -q`

---

**UNAI** — *Unmanned Navigation & Autonomous Intelligence*.
