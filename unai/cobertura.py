"""Misión de cobertura: la ruta de barrido y el mapa de lo ya reconocido.

El enjambre barre como una sola brocha cuyo ancho lo da el frente de la
formación más la huella de la cámara. La ruta es un zigzag, y el cambio de
pasada se hace **en espejo**: la formación no rota, invierte su sentido de
avance y se desplaza de lado. Rotar un frente de 1 km obligaría al dron
exterior a recorrer un semicírculo de 1.555 m volando a tope mientras el
interior casi se para (`docs/04`, §4).
"""

from __future__ import annotations

import math

import numpy as np

from .calculo import Motor
from .config import ConfigEntorno
from .formacion import Formacion

SIN_VISITAR = -1


class RutaBarrido:
    """Zigzag sobre la zona, recorrido por un punto guía.

    El guía no avanza a ciegas: si el enjambre se queda atrás —porque está
    esquivando un bosque, por ejemplo— el guía frena para esperarlo. Sin eso,
    la ruta se completaría sobre el papel con los drones a kilómetros de sus
    puestos.
    """

    def __init__(
        self,
        cfg: ConfigEntorno,
        formacion: Formacion,
        huella_m: float,
        v_crucero: float,
        tolerancia_retraso_m: float | None = None,
        a_curva: float = 4.9,
        v_min_giro: float = 1.0,
    ):
        self.v_crucero = float(v_crucero)
        self.a_curva = float(a_curva)
        self.v_min_giro = float(v_min_giro)
        self.altura = formacion.altura_m
        self.ancho_pasada = formacion.frente_m + huella_m
        self.tolerancia = tolerancia_retraso_m or max(3.0 * huella_m, 15.0)

        self.n_pasadas = max(1, math.ceil(cfg.lado_y_m / self.ancho_pasada))
        # Se reparten las pasadas por igual en vez de dejar que la última
        # sobresalga: ajustar el paso a un divisor del lado es gratis y evita
        # desperdiciar hasta un cuarto del último recorrido.
        self.paso_pasada = cfg.lado_y_m / self.n_pasadas

        puntos: list[tuple[float, float]] = []
        for k in range(self.n_pasadas):
            y = (k + 0.5) * self.paso_pasada
            if k % 2 == 0:
                puntos += [(0.0, y), (cfg.lado_x_m, y)]
            else:
                puntos += [(cfg.lado_x_m, y), (0.0, y)]
        self.puntos = np.array(puntos, dtype=np.float64)

        tramos = np.diff(self.puntos, axis=0)
        self.longitud_tramo = np.linalg.norm(tramos, axis=1)
        self.acumulado = np.concatenate(([0.0], np.cumsum(self.longitud_tramo)))
        self.longitud_total = float(self.acumulado[-1])

        self._s = 0.0
        self._sentido = 1.0
        self._velocidad = np.zeros(3)

    # -- estado ------------------------------------------------------------- #

    @property
    def recorrido_m(self) -> float:
        return self._s

    @property
    def completada(self) -> bool:
        return self._s >= self.longitud_total

    @property
    def progreso(self) -> float:
        return min(1.0, self._s / max(self.longitud_total, 1e-9))

    @property
    def sentido(self) -> float:
        """+1 o −1: hacia dónde mira la formación. Invertirlo es el giro en espejo."""
        return self._sentido

    def guia(self) -> np.ndarray:
        """Posición actual del punto guía de la formación."""
        s = min(self._s, self.longitud_total)
        i = int(np.searchsorted(self.acumulado, s, side="right") - 1)
        i = max(0, min(i, len(self.longitud_tramo) - 1))
        largo = self.longitud_tramo[i]
        fraccion = 0.0 if largo <= 1e-9 else (s - self.acumulado[i]) / largo
        punto = self.puntos[i] + (self.puntos[i + 1] - self.puntos[i]) * fraccion
        return np.array([punto[0], punto[1], self.altura])

    def avanzar(self, dt: float, retraso_m: float) -> None:
        """Adelanta el guía, frenando en proporción al retraso del enjambre."""
        freno = max(0.0, 1.0 - max(0.0, retraso_m) / self.tolerancia)
        rapidez = self.v_crucero * freno

        # Frenada antes de la esquina, por el mismo principio de distancia de
        # frenado que emplea la evitación de obstáculos. Sin ella el guía toma
        # el giro en seco y el enjambre se pasa de largo: revertir 15 m/s con
        # 9,81 m/s² cuesta v²/2a = 11,5 metros como mínimo físico, y el error
        # de formación saltaba de 0,01 m en recta a 16 m en cada giro.
        rapidez = min(rapidez, self._limite_por_curva())
        self._s = min(self._s + rapidez * dt, self.longitud_total)

        i = int(np.searchsorted(self.acumulado, min(self._s, self.longitud_total), side="right") - 1)
        i = max(0, min(i, len(self.longitud_tramo) - 1))
        tramo = self.puntos[i + 1] - self.puntos[i]
        largo = self.longitud_tramo[i]
        if largo > 1e-9:
            self._velocidad = np.array([tramo[0], tramo[1], 0.0]) / largo * rapidez
        if abs(tramo[0]) > 1e-9:
            self._sentido = math.copysign(1.0, tramo[0])

    def _limite_por_curva(self) -> float:
        """Velocidad máxima compatible con detenerse en el próximo vértice."""
        s = min(self._s, self.longitud_total)
        i = int(np.searchsorted(self.acumulado, s, side="right") - 1)
        i = max(0, min(i, len(self.longitud_tramo) - 1))
        if i >= len(self.longitud_tramo) - 1:
            return self.v_crucero          # último tramo: no hay esquina que doblar
        restante = max(self.acumulado[i + 1] - s, 0.0)
        return max(self.v_min_giro, math.sqrt(2.0 * self.a_curva * restante))

    def velocidad_guia(self) -> np.ndarray:
        """Velocidad actual del puesto, para que el dron la anticipe.

        Sin este dato, la ley de guiado sería puramente proporcional al error
        de posición y la formación volaría permanentemente rezagada: el dron
        solo acelera si ya va retrasado, así que el retraso nunca desaparece.
        Anticipando la velocidad del puesto, el error de seguimiento tiende a
        cero y el guía deja de frenar.
        """
        return self._velocidad.copy()

    def tiempo_estimado_s(self) -> float:
        """Duración ideal de la misión, sin frenadas ni rodeos."""
        return self.longitud_total / max(self.v_crucero, 1e-9)


class MallaCobertura:
    """Mapa de la zona con el instante de la primera visita a cada celda.

    Guardar el instante y no un simple sí/no es lo que permite dibujar en el
    visor cómo se va pintando el mapa y trazar la curva de cobertura
    (`docs/03`, §2.2).
    """

    def __init__(self, cfg: ConfigEntorno, celda_m: float, radio_huella_m: float, motor: Motor):
        self.motor = motor
        self.xp = motor.xp
        self.celda = float(celda_m)
        self.n_x = max(1, int(math.ceil(cfg.lado_x_m / self.celda)))
        self.n_y = max(1, int(math.ceil(cfg.lado_y_m / self.celda)))
        self.n_celdas = self.n_x * self.n_y
        self.visita = self.xp.full(self.n_celdas, SIN_VISITAR, dtype=self.xp.int32)
        self._visitadas = 0
        self._sello = -1
        self._contado_en = -2

        self.radio_huella = float(radio_huella_m)
        # Ventana de celdas candidatas alrededor del dron. No basta con una
        # plantilla fija de celdas "dentro del círculo": eso marcaría siempre
        # el mismo número de celdas fuera cual fuese la posición del dron
        # dentro de su celda, y sobrestimaría la superficie cubierta en un
        # 59 % con celdas de 5 m. La pertenencia se decide midiendo la
        # distancia real del dron al centro de cada celda candidata.
        alcance = int(math.ceil(radio_huella_m / self.celda)) + 1
        rejilla = np.arange(-alcance, alcance + 1)
        dx, dy = np.meshgrid(rejilla, rejilla, indexing="xy")
        self.ventana_x = self.xp.asarray(dx.ravel().astype(np.int64))
        self.ventana_y = self.xp.asarray(dy.ravel().astype(np.int64))

    def marcar(self, posiciones, paso: int) -> None:
        """Anota como visitadas las celdas que ve cada dron en este instante."""
        xp = self.xp
        cx = (posiciones[:, 0] / self.celda).astype(xp.int64)[:, None] + self.ventana_x[None, :]
        cy = (posiciones[:, 1] / self.celda).astype(xp.int64)[:, None] + self.ventana_y[None, :]

        # Distancia del dron al CENTRO de cada celda candidata: así la celda
        # se marca o no según dónde esté el dron de verdad, y la superficie
        # medida coincide con la huella real.
        ex = (cx.astype(posiciones.dtype) + 0.5) * self.celda - posiciones[:, 0:1]
        ey = (cy.astype(posiciones.dtype) + 0.5) * self.celda - posiciones[:, 1:2]
        cubierta = (ex * ex + ey * ey) <= self.radio_huella**2

        valida = cubierta & (cx >= 0) & (cx < self.n_x) & (cy >= 0) & (cy < self.n_y)
        plano = xp.where(valida, cy * self.n_x + cx, 0).ravel()
        nueva = valida.ravel() & (self.visita[plano] == SIN_VISITAR)
        self.visita[plano[nueva]] = paso
        self._sello = paso

    @property
    def visitadas(self) -> int:
        """Celdas ya reconocidas.

        Se cuenta al preguntar y se recuerda hasta el siguiente marcado. Contar
        de forma incremental exigiría descartar los índices repetidos de cada
        paso, y ordenarlos cuesta más que el recuento entero: la cobertura solo
        se consulta al muestrear, una vez cada diez pasos.
        """
        if self._sello != self._contado_en:
            self._visitadas = int((self.visita != SIN_VISITAR).sum())
            self._contado_en = self._sello
        return self._visitadas

    @property
    def porcentaje(self) -> float:
        return 100.0 * self.visitadas / self.n_celdas

    def a_numpy(self) -> np.ndarray:
        return self.motor.a_numpy(self.visita).reshape(self.n_y, self.n_x)
