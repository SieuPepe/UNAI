"""Modelo de vuelo: cómo responde un dron a la aceleración que se le pide.

La interfaz `ModeloVuelo` es la costura por la que el simulador se puede hacer
más realista sin tocar nada más (`docs/01`, §2): el resto del programa solo
sabe pedir "intenta acelerar así durante este intervalo" y leer dónde ha
acabado el dron. Sustituir el modelo cinemático por un cuadricóptero de seis
grados de libertad es reemplazar esta pieza.
"""

from __future__ import annotations

from typing import Protocol

from .calculo import Motor
from .config import ConfigDron


class ModeloVuelo(Protocol):
    """Contrato que debe cumplir cualquier modelo de vuelo."""

    def avanzar(self, posicion, velocidad_aire, aceleracion, viento, dt: float):
        """Devuelve (posicion, velocidad_aire) tras un paso de tiempo."""
        ...


class ModeloCinematico:
    """Punto con masa sujeto a los límites físicos del aparato.

    No simula rotores ni actitud: aplica la aceleración pedida recortada a lo
    que el aparato puede dar. Con esto caben cientos de drones a velocidad
    cómoda, que es lo que hace falta para estudiar comportamiento de enjambre.
    """

    def __init__(self, cfg: ConfigDron, motor: Motor):
        self.cfg = cfg
        self.motor = motor
        self.xp = motor.xp

    def avanzar(self, posicion, velocidad_aire, aceleracion, viento, dt: float):
        xp = self.xp
        a = self._saturar(aceleracion, self.cfg.a_max_ms2)
        v = velocidad_aire + a * dt
        v = self._limitar_giro(velocidad_aire, v, dt)
        v = self._limitar_velocidad(v)

        # El dron controla su velocidad respecto al AIRE; sobre el terreno se
        # mueve con la suma de esa velocidad y la del aire (`docs/02`, §8).
        velocidad_suelo = v + viento
        return posicion + velocidad_suelo * dt, v

    def velocidad_suelo(self, velocidad_aire, viento):
        return velocidad_aire + viento

    # -- saturaciones ------------------------------------------------------- #

    def _saturar(self, vector, maximo: float):
        """Recorta la longitud conservando la dirección.

        Truncar cada eje por separado deformaría la dirección y el dron
        acabaría acelerando hacia donde no quería (`docs/02`, §5).
        """
        xp = self.xp
        norma = xp.linalg.norm(vector, axis=-1, keepdims=True)
        factor = xp.minimum(1.0, maximo / xp.maximum(norma, 1e-12))
        return vector * factor

    def _limitar_velocidad(self, v):
        """Límite horizontal y vertical por separado.

        Un multirrotor sube mucho más despacio de lo que avanza, y baja aún
        más despacio para no entrar en su propia estela.
        """
        xp = self.xp
        horizontal = v[:, :2]
        norma = xp.linalg.norm(horizontal, axis=-1, keepdims=True)
        factor = xp.minimum(1.0, self.cfg.v_max_horizontal_ms / xp.maximum(norma, 1e-12))
        vertical = xp.clip(v[:, 2], -self.cfg.v_max_descenso_ms, self.cfg.v_max_ascenso_ms)
        return xp.concatenate([horizontal * factor, vertical[:, None]], axis=1)

    def _limitar_giro(self, v_antigua, v_nueva, dt: float):
        """Un dron no cambia de rumbo al instante: se limita el giro en planta."""
        xp = self.xp
        maximo = self.cfg.giro_max_rad_s * dt
        if maximo >= 3.14159:
            return v_nueva

        a_xy, n_xy = v_antigua[:, :2], v_nueva[:, :2]
        norma_a = xp.linalg.norm(a_xy, axis=-1)
        norma_n = xp.linalg.norm(n_xy, axis=-1)
        # Un dron casi parado no tiene rumbo que conservar: puede apuntar a
        # donde quiera sin violar ningún límite físico.
        aplicable = (norma_a > 1e-3) & (norma_n > 1e-9)

        coseno = xp.clip(
            (a_xy * n_xy).sum(axis=-1) / xp.maximum(norma_a * norma_n, 1e-12), -1.0, 1.0
        )
        angulo = xp.arccos(coseno)
        exceso = xp.maximum(angulo - maximo, 0.0)
        # Signo del giro: producto vectorial en 2D.
        sentido = xp.sign(a_xy[:, 0] * n_xy[:, 1] - a_xy[:, 1] * n_xy[:, 0])
        giro = xp.where(aplicable, -sentido * exceso, 0.0)

        cos_g, sin_g = xp.cos(giro), xp.sin(giro)
        rot_x = n_xy[:, 0] * cos_g - n_xy[:, 1] * sin_g
        rot_y = n_xy[:, 0] * sin_g + n_xy[:, 1] * cos_g
        return xp.stack([rot_x, rot_y, v_nueva[:, 2]], axis=1)
