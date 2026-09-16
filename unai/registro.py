"""Registro de trayectorias para el visor.

La física se calcula a 50 Hz, pero las trayectorias se guardan a 5 Hz y el
visor interpola: el ojo no distingue la diferencia y el fichero pesa diez veces
menos. Las posiciones se guardan como enteros de 16 bits referidos a los
límites de la zona, lo que sobre 3.162 metros da una precisión de 4,8 cm, muy
por encima de lo que necesita un dibujo (`docs/04`, §9).
"""

from __future__ import annotations

import numpy as np

from .calculo import Motor

_RANGO = 65535.0
_MINIMO = -32768


class RegistroTrayectorias:
    """Acumula las posiciones muestreadas y las cuantiza a 16 bits."""

    def __init__(self, motor: Motor, limites_min: np.ndarray, limites_max: np.ndarray):
        self.motor = motor
        self.minimo = np.asarray(limites_min, dtype=np.float64)
        self.maximo = np.asarray(limites_max, dtype=np.float64)
        self.escala = np.maximum(self.maximo - self.minimo, 1e-6)
        self.instantes: list[float] = []
        self._marcos: list[np.ndarray] = []

    def anotar(self, t: float, posiciones) -> None:
        p = self.motor.a_numpy(posiciones)
        normal = np.clip((p - self.minimo) / self.escala, 0.0, 1.0)
        self._marcos.append((normal * _RANGO + _MINIMO).astype(np.int16))
        self.instantes.append(t)

    @property
    def n_marcos(self) -> int:
        return len(self._marcos)

    def datos(self) -> np.ndarray:
        """(n_marcos, n_drones, 3) en enteros de 16 bits."""
        if not self._marcos:
            return np.empty((0, 0, 3), dtype=np.int16)
        return np.stack(self._marcos)

    def a_dict(self) -> dict:
        datos = self.datos()
        return {
            "n_marcos": int(datos.shape[0]),
            "n_drones": int(datos.shape[1]) if datos.size else 0,
            "instantes": [round(t, 3) for t in self.instantes],
            "minimo": self.minimo.tolist(),
            "escala": self.escala.tolist(),
            "datos": datos,
        }

    def descuantizar(self) -> np.ndarray:
        """Devuelve las posiciones en metros: para comprobar el error introducido."""
        datos = self.datos().astype(np.float64)
        return (datos - _MINIMO) / _RANGO * self.escala + self.minimo

    @property
    def bytes_estimados(self) -> int:
        return self.datos().nbytes
