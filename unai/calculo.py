"""Selección del dispositivo de cálculo: CPU (NumPy) o GPU (CuPy).

El motor está escrito contra un módulo de matrices intercambiable, de modo que
el mismo código corre en la CPU o en una GPU de NVIDIA sin cambiar una línea.

Cuándo compensa la GPU
----------------------
La GPU no acelera por ser GPU: acelera cuando hay suficiente trabajo por
operación para amortizar el coste de lanzarla. Cada llamada a una función
sobre matrices cuesta del orden de 5-10 microsegundos en despacharse al chip,
se opere sobre diez números o sobre diez millones.

El caso de referencia de este proyecto son 100 drones, es decir matrices de
100 filas: cada operación se resuelve en la CPU en menos de lo que tarda la
GPU en recibir la orden, y el paso de simulación encadena decenas de
operaciones. **A 100 drones la GPU es más lenta que la CPU.** Empieza a
compensar a partir de varios miles de drones, o con campos de obstáculos muy
densos donde la consulta de vecindad domina el coste.

`banco_de_pruebas.py` mide el punto de cruce en la máquina concreta.

Reproducibilidad
----------------
Todo el azar (colocación de obstáculos, viento, ruido) se genera en la CPU con
un generador sembrado y luego se transfiere. Así, la misma semilla produce
exactamente el mismo escenario y la misma secuencia de ráfagas en ambos
dispositivos. Lo que sí puede variar en los últimos bits es el resultado de
las sumas en coma flotante, porque la GPU las acumula en otro orden. Dos
ejecuciones en el mismo dispositivo son idénticas; entre dispositivos, son
equivalentes pero no idénticas bit a bit.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np


class Motor:
    """Envoltorio del módulo de matrices en uso."""

    def __init__(self, xp: Any, nombre: str, descripcion: str):
        self.xp = xp
        self.nombre = nombre
        self.descripcion = descripcion

    @property
    def es_gpu(self) -> bool:
        return self.nombre == "gpu"

    def array(self, datos, dtype=np.float64):
        """Lleva datos al dispositivo."""
        return self.xp.asarray(np.asarray(datos, dtype=dtype))

    def a_numpy(self, datos) -> np.ndarray:
        """Trae datos de vuelta a la CPU para guardarlos o medirlos."""
        if self.es_gpu:
            return self.xp.asnumpy(datos)
        return np.asarray(datos)

    def sincronizar(self) -> None:
        """Espera a que la GPU termine. Imprescindible antes de cronometrar."""
        if self.es_gpu:
            self.xp.cuda.runtime.deviceSynchronize()

    def __repr__(self) -> str:
        return f"Motor({self.nombre}: {self.descripcion})"


def _motor_cpu() -> Motor:
    return Motor(np, "cpu", f"NumPy {np.__version__}")


def gpu_disponible() -> tuple[bool, str]:
    """Indica si hay GPU utilizable y por qué no, si no la hay."""
    try:
        import cupy
    except ImportError:
        return False, "CuPy no está instalado (pip install cupy-cuda12x)"
    try:
        n = cupy.cuda.runtime.getDeviceCount()
    except Exception as exc:  # driver ausente, versión incompatible, etc.
        return False, f"CuPy está instalado pero no encuentra GPU utilizable: {exc}"
    if n < 1:
        return False, "CuPy no detecta ninguna GPU"
    try:
        nombre = cupy.cuda.runtime.getDeviceProperties(0)["name"].decode()
    except Exception:
        nombre = "GPU CUDA"
    return True, f"CuPy {cupy.__version__} sobre {nombre}"


def seleccionar(usar_gpu: bool = False, silencioso: bool = False) -> Motor:
    """Elige el dispositivo de cálculo.

    Con `usar_gpu` falso se usa la CPU sin más. Con `usar_gpu` cierto se
    intenta la GPU y, si no la hay, se avisa **de forma visible** y se sigue en
    CPU: un respaldo silencioso haría que una comparación de rendimiento
    mintiera sin que nadie se enterase.
    """
    if not usar_gpu:
        return _motor_cpu()

    hay, motivo = gpu_disponible()
    if not hay:
        if not silencioso:
            warnings.warn(
                f"Se pidió GPU pero no está disponible: {motivo}. "
                f"La simulación continúa en CPU.",
                RuntimeWarning,
                stacklevel=2,
            )
        return _motor_cpu()

    import cupy
    return Motor(cupy, "gpu", motivo)
