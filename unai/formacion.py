"""Geometría de la formación: qué puesto ocupa cada dron.

La forma de la formación es el parámetro de mayor impacto del proyecto, porque
decide el frente de barrido y con él el tiempo de misión: entre 17 minutos en
línea y casi cinco horas en columna, con los mismos drones y la misma zona
(`docs/04`, §4).

Marco local: `x` hacia adelante (avance), `y` a la izquierda (el frente), `z`
vertical. El enjambre no rota al cambiar de pasada —da el giro en espejo— así
que el marco local se proyecta al mundo sin rotación, solo invirtiendo el eje
de avance.
"""

from __future__ import annotations

import math

import numpy as np

from .calculo import Motor
from .config import ConfigFormacion


class Formacion:
    """Puestos de los drones y su proyección al mundo."""

    def __init__(self, cfg: ConfigFormacion, n_drones: int, altura_m: float, motor: Motor):
        cfg.validar(n_drones)
        self.cfg = cfg
        self.n_drones = n_drones
        self.altura_m = float(altura_m)
        self.motor = motor
        self.xp = motor.xp

        locales = _puestos(cfg, n_drones)
        locales[:, 2] = 0.0
        self.locales_np = locales
        self.locales = motor.array(locales)

    @property
    def frente_m(self) -> float:
        """Anchura del frente de barrido, de extremo a extremo."""
        if self.n_drones < 2:
            return 0.0
        return float(self.locales_np[:, 1].max() - self.locales_np[:, 1].min())

    @property
    def fondo_m(self) -> float:
        if self.n_drones < 2:
            return 0.0
        return float(self.locales_np[:, 0].max() - self.locales_np[:, 0].min())

    def en_mundo(self, guia, sentido: float):
        """Puestos absolutos dado el punto guía y el sentido de avance.

        `sentido` vale +1 o −1. Invertirlo refleja la formación respecto a su
        eje lateral: es el **giro en espejo**, que evita que el dron exterior
        de un frente de 1 km tenga que recorrer un semicírculo mientras el
        interior casi se para (`docs/04`, §4).
        """
        xp = self.xp
        desplazado = xp.stack(
            [self.locales[:, 0] * sentido, self.locales[:, 1], self.locales[:, 2]], axis=1
        )
        return desplazado + xp.asarray(guia)[None, :]


def _puestos(cfg: ConfigFormacion, n: int) -> np.ndarray:
    return {
        "linea": _linea,
        "rejilla": _rejilla,
        "cuna": _cuna,
    }[cfg.forma](cfg, n)


def _linea(cfg: ConfigFormacion, n: int) -> np.ndarray:
    """Todos en ala: maximiza el frente por dron, que es lo que barre."""
    i = np.arange(n, dtype=np.float64)
    puestos = np.zeros((n, 3))
    puestos[:, 1] = (i - (n - 1) / 2.0) * cfg.separacion_max_m
    return puestos


def _rejilla(cfg: ConfigFormacion, n: int) -> np.ndarray:
    """Bloque de filas × columnas. La profundidad es anchura desaprovechada."""
    columnas = int(cfg.columnas)
    i = np.arange(n)
    fila, columna = i // columnas, i % columnas
    puestos = np.zeros((n, 3))
    puestos[:, 0] = -fila * cfg.separacion_max_m
    puestos[:, 1] = (columna - (columnas - 1) / 2.0) * cfg.separacion_max_m
    return puestos


def _cuna(cfg: ConfigFormacion, n: int) -> np.ndarray:
    """En V, con el vértice al frente: reparte la estela y facilita el giro."""
    angulo = math.radians(cfg.angulo_cuna_grados)
    i = np.arange(n)
    rango = (i + 1) // 2
    lado = np.where(i % 2 == 0, 1.0, -1.0)
    lado[0] = 0.0
    puestos = np.zeros((n, 3))
    puestos[:, 0] = -rango * cfg.separacion_max_m * math.sin(angulo)
    puestos[:, 1] = lado * rango * cfg.separacion_max_m * math.cos(angulo)
    return puestos
