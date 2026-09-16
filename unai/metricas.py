"""Métricas de la misión: los números con los que se comparan configuraciones.

Se fijan antes de programar a propósito. Añadidas al final saldrían las
fáciles de calcular, no las que importan, y una métrica mal elegida lleva a
conclusiones falsas con toda la apariencia de rigor (`docs/03`, §1).

Toda métrica de seguridad va acompañada de una de eficacia: optimizar "cero
colisiones" sin mirar nada más produce un enjambre perfecto que nunca choca
porque tampoco cumple la misión.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .calculo import Motor
from .config import Config

_BIN_M = 0.05
_N_BINS = 4000          # hasta 200 m de separación entre vecinos


@dataclass
class SerieTemporal:
    """Evolución de las magnitudes clave, muestreada a la frecuencia de registro."""

    t: list[float] = field(default_factory=list)
    cobertura: list[float] = field(default_factory=list)
    separacion_minima: list[float] = field(default_factory=list)
    error_formacion: list[float] = field(default_factory=list)
    polarizacion: list[float] = field(default_factory=list)
    energia_wh: list[float] = field(default_factory=list)
    progreso: list[float] = field(default_factory=list)
    bloqueados: list[int] = field(default_factory=list)


class Metricas:
    """Acumula los indicadores paso a paso.

    Las métricas se calculan a la frecuencia completa de la simulación, no a la
    de registro: la distancia mínima entre drones no se puede muestrear, o se
    pasa por alto justo el instante del roce (`docs/04`, §6).
    """

    def __init__(self, cfg: Config, motor: Motor):
        self.cfg = cfg
        self.motor = motor
        self.xp = motor.xp
        self.n = cfg.enjambre.n_drones
        self.dt = cfg.simulacion.dt_s

        d = cfg.enjambre.dron
        self.diametro = 2.0 * d.radio_m
        self.d_seguridad = cfg.comportamiento.anti_distancia_seguridad_m
        self.d_max = cfg.enjambre.formacion.separacion_max_m

        # Potencia de sostenimiento por la teoría del disco actuador. Es la
        # parte dominante: un multirrotor gasta casi lo mismo parado en el aire
        # que avanzando, porque casi toda la energía se va en no caerse.
        rho = 1.225
        empuje = d.masa_kg * 9.81
        self.p_sostener = (empuje**1.5) / math.sqrt(2.0 * rho * d.area_rotores_m2)
        self.p_sostener /= max(d.figura_merito, 1e-6)
        # Coste añadido por avanzar, con la forma física del arrastre. Sumarlo
        # sin más al sostenimiento sobrestima: en avance el multirrotor gana
        # sustentación de traslación y necesita menos potencia inducida, de
        # modo que el consumo real a 15 m/s ronda 1,4 veces el de estacionario
        # y no 2,5. Los coeficientes están ajustados a esa proporción.
        self.k_avance = 0.5 * rho * d.coef_arrastre * d.area_frontal_m2 / 0.7

        self.pasos = 0
        self.separacion_minima = math.inf
        self.pasos_riesgo = 0
        self.pasos_colision_drones = 0
        self.pasos_colision_entorno = 0
        self.episodios_colision_drones = 0
        self.episodios_colision_entorno = 0
        self.separacion_vecino_maxima = 0.0
        self.pasos_fuera_formacion = 0
        self.error_formacion_acumulado = 0.0
        self.energia_wh = 0.0
        self.energia_por_dron = np.zeros(self.n)
        self.pasos_bloqueado = np.zeros(self.n)
        self.distancia_recorrida = np.zeros(self.n)
        self._hist = np.zeros(_N_BINS, dtype=np.int64)
        self._colision_previa_drones = np.zeros(self.n, dtype=bool)
        self._colision_previa_entorno = np.zeros(self.n, dtype=bool)
        self.serie = SerieTemporal()

    # -- acumulación -------------------------------------------------------- #

    def paso(
        self,
        distancia_vecino,
        colision_entorno,
        error_puesto,
        velocidad_aire,
        velocidad_suelo,
    ) -> None:
        """Acumula los indicadores de un paso de simulación."""
        xp = self.xp
        self.pasos += 1
        a_np = self.motor.a_numpy

        vecino = a_np(distancia_vecino)
        finito = np.isfinite(vecino)
        if finito.any():
            minimo = float(vecino[finito].min())
            self.separacion_minima = min(self.separacion_minima, minimo)
            if minimo < self.d_seguridad:
                self.pasos_riesgo += 1
            self.separacion_vecino_maxima = max(
                self.separacion_vecino_maxima, float(vecino[finito].max())
            )
            indices = np.clip((vecino[finito] / _BIN_M).astype(np.int64), 0, _N_BINS - 1)
            self._hist += np.bincount(indices, minlength=_N_BINS)

        # Formación: cuántos drones están más lejos de lo tolerado de su vecino
        # más próximo. Que se deshaga y se rehaga es un resultado legítimo; lo
        # interesante es medir cuánto y cuándo (`docs/04`, §5).
        desgajados = finito & (vecino > self.d_max + self.cfg.comportamiento.cohesion_holgura)
        self.pasos_fuera_formacion += int(desgajados.sum())

        choque_drones = finito & (vecino < self.diametro)
        self.pasos_colision_drones += int(choque_drones.sum())
        self.episodios_colision_drones += int((choque_drones & ~self._colision_previa_drones).sum())
        self._colision_previa_drones = choque_drones

        entorno = a_np(colision_entorno)
        self.pasos_colision_entorno += int(entorno.sum())
        self.episodios_colision_entorno += int((entorno & ~self._colision_previa_entorno).sum())
        self._colision_previa_entorno = entorno

        self.error_formacion_acumulado += float(a_np(error_puesto).mean())

        v_aire = a_np(xp.linalg.norm(velocidad_aire, axis=1))
        v_suelo = a_np(xp.linalg.norm(velocidad_suelo, axis=1))
        potencia = self.p_sostener + self.k_avance * v_aire**3
        consumo = potencia * self.dt / 3600.0
        self.energia_por_dron += consumo
        self.energia_wh += float(consumo.sum())
        self.distancia_recorrida += v_suelo * self.dt
        self.pasos_bloqueado += (v_suelo < self.cfg.comportamiento.bloqueo_umbral_ms).astype(float)

    def muestrear(
        self, t: float, cobertura: float, error_puesto, velocidad_suelo, progreso: float
    ) -> None:
        """Anota un punto de la serie temporal, a la frecuencia de registro."""
        a_np = self.motor.a_numpy
        v = a_np(velocidad_suelo)
        rapidez = np.linalg.norm(v, axis=1)
        activos = rapidez > 1e-6
        # Polarización: se promedian las direcciones de vuelo y se mide la
        # longitud del resultado. 1 = todos al unísono, 0 = desordenados.
        if activos.any():
            direcciones = v[activos] / rapidez[activos][:, None]
            polarizacion = float(np.linalg.norm(direcciones.mean(axis=0)))
        else:
            polarizacion = 0.0

        s = self.serie
        s.t.append(t)
        s.cobertura.append(cobertura)
        s.separacion_minima.append(
            self.separacion_minima if math.isfinite(self.separacion_minima) else 0.0
        )
        s.error_formacion.append(float(a_np(error_puesto).mean()))
        s.polarizacion.append(polarizacion)
        s.energia_wh.append(self.energia_wh)
        s.progreso.append(progreso)
        s.bloqueados.append(int((rapidez < self.cfg.comportamiento.bloqueo_umbral_ms).sum()))

    # -- resultados --------------------------------------------------------- #

    def percentil_separacion(self, percentil: float) -> float:
        """Percentil de la distancia al vecino más cercano.

        El mínimo absoluto es un único número sensible a un caso aislado; el
        percentil 5 describe el comportamiento habitual y es más robusto.
        Conviene mirar los dos (`docs/03`, §2.1).
        """
        total = self._hist.sum()
        if total == 0:
            return 0.0
        objetivo = percentil / 100.0 * total
        acumulado = np.cumsum(self._hist)
        indice = int(np.searchsorted(acumulado, objetivo))
        return (min(indice, _N_BINS - 1) + 0.5) * _BIN_M

    def resumen(self, cobertura_final: float, tiempo_s: float, superficie_m2: float) -> dict:
        segundos = self.pasos * self.dt
        dron_segundos = max(self.pasos * self.n * self.dt, 1e-9)
        autonomia = self.cfg.enjambre.dron.bateria_wh
        peor = float(self.energia_por_dron.max()) if self.n else 0.0
        cubierto_m2 = superficie_m2 * cobertura_final / 100.0

        return {
            "seguridad": {
                "colisiones_entre_drones": self.episodios_colision_drones,
                "colisiones_con_entorno": self.episodios_colision_entorno,
                "separacion_minima_m": (
                    round(self.separacion_minima, 3)
                    if math.isfinite(self.separacion_minima) else None
                ),
                "margen_seguridad_p5_m": round(self.percentil_separacion(5.0), 3),
                "separacion_mediana_m": round(self.percentil_separacion(50.0), 3),
                "tiempo_en_riesgo_s": round(self.pasos_riesgo * self.dt, 2),
            },
            "eficacia": {
                "cobertura_final_pct": round(cobertura_final, 2),
                "tiempo_mision_s": round(tiempo_s, 1),
                "tiempo_hasta_90pct_s": self._tiempo_hasta(90.0),
                "tiempo_hasta_99pct_s": self._tiempo_hasta(99.0),
            },
            "coste": {
                "energia_total_wh": round(self.energia_wh, 2),
                "energia_por_m2_cubierto_wh": (
                    round(self.energia_wh / cubierto_m2, 6) if cubierto_m2 > 0 else None
                ),
                "bateria_restante_minima_pct": round(100.0 * (1.0 - peor / autonomia), 1),
                "autonomia_excedida": bool(peor > autonomia),
                "distancia_media_por_dron_m": round(float(self.distancia_recorrida.mean()), 1),
            },
            "formacion": {
                "error_medio_al_puesto_m": round(
                    self.error_formacion_acumulado / max(self.pasos, 1), 3
                ),
                "separacion_vecino_maxima_m": round(self.separacion_vecino_maxima, 2),
                "fraccion_tiempo_fuera_de_formacion": round(
                    self.pasos_fuera_formacion / dron_segundos * self.dt, 4
                ),
                "polarizacion_media": (
                    round(float(np.mean(self.serie.polarizacion)), 3)
                    if self.serie.polarizacion else None
                ),
                "tiempo_bloqueado_medio_s": round(
                    float(self.pasos_bloqueado.mean()) * self.dt, 2
                ),
            },
            "simulacion": {
                "pasos": self.pasos,
                "segundos_simulados": round(segundos, 2),
            },
        }

    def _tiempo_hasta(self, objetivo: float) -> float | None:
        for t, c in zip(self.serie.t, self.serie.cobertura):
            if c >= objetivo:
                return round(t, 1)
        return None
