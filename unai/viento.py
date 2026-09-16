"""Viento medio con perfil de altura y turbulencia con memoria.

La turbulencia se genera con un proceso de Ornstein-Uhlenbeck (`docs/02`, §8):
un número aleatorio nuevo en cada paso no se parecería al viento, temblaría
como una televisión sin señal. El viento real tiene memoria, y eso es lo que
aporta el término que arrastra el valor anterior.
"""

from __future__ import annotations

import math

import numpy as np

from .calculo import Motor
from .config import ConfigViento


class Viento:
    """Campo de viento uniforme en planta y variable con la altura.

    Las ráfagas se sortean siempre en la CPU con un generador sembrado, de modo
    que la misma semilla produce la misma secuencia de viento en cualquier
    dispositivo de cálculo.
    """

    def __init__(self, cfg: ConfigViento, motor: Motor, semilla: int):
        self.cfg = cfg
        self.motor = motor
        self.xp = motor.xp
        self._azar = np.random.default_rng(semilla)
        self._rafaga = np.zeros(3)

        angulo = math.radians(cfg.direccion_grados)
        self._direccion = np.array([math.cos(angulo), math.sin(angulo), 0.0])

    def avanzar(self, dt: float) -> None:
        """Hace evolucionar la ráfaga un paso de tiempo.

            w(t+dt) = w(t)·(1 − dt/T) + sigma·raíz(2·dt/T)·N(0,1)

        El primer término tira hacia la calma y el segundo desordena; el
        equilibrio entre ambos produce algo que se parece a un anemómetro real.
        """
        sigma = self.cfg.turbulencia_sigma_ms
        if sigma <= 0.0:
            return
        tau = max(self.cfg.tiempo_correlacion_s, 1e-6)
        decaimiento = min(dt / tau, 1.0)
        self._rafaga = self._rafaga * (1.0 - decaimiento) + sigma * math.sqrt(
            2.0 * decaimiento
        ) * self._azar.standard_normal(3)

    def en(self, posiciones):
        """Vector de viento en la posición de cada dron, en m/s.

        El perfil de altura sigue la ley de potencia: el rozamiento con el
        terreno frena el viento abajo, y por eso volar bajo entre edificios
        protege del viento y subir para esquivar tiene un coste.
        """
        xp = self.xp
        n = posiciones.shape[0]
        if self.cfg.velocidad_media_ms <= 0.0 and not self._rafaga.any():
            return xp.zeros((n, 3))

        altura = xp.maximum(posiciones[:, 2], 0.1)
        factor = (altura / max(self.cfg.altura_referencia_m, 1e-6)) ** self.cfg.exponente_alfa
        medio = (
            self.motor.array(self._direccion)[None, :]
            * (self.cfg.velocidad_media_ms * factor)[:, None]
        )
        return medio + self.motor.array(self._rafaga)[None, :]

    @property
    def rafaga_actual(self) -> np.ndarray:
        return self._rafaga.copy()
