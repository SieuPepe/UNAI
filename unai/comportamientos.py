"""Los comportamientos del enjambre, expresados como aceleraciones que se suman.

Cada comportamiento produce una aceleración con su propio peso, y el total es
la suma (`docs/02`, §4). Los pesos son los mandos que definen el carácter del
enjambre: subir el de anticolisión da drones prudentes que cumplen mal la
misión; subir el del puesto da drones eficientes que rozan el choque.

Los vecinos se buscan con la matriz densa de todas las distancias. A 100 drones
son 10.000 números que se calculan de una vez, y montar una rejilla espacial
saldría más lento por el sobrecoste de recorrerla desde Python (`docs/04`, §9).
Por encima de unos 2.000 drones la matriz deja de caber con holgura y entonces
sí toca la rejilla.
"""

from __future__ import annotations

from dataclasses import dataclass

from .calculo import Motor
from .config import ConfigComportamiento, ConfigEnjambre
from .entorno import Vecindad


@dataclass
class VecindadDrones:
    """Relaciones entre drones dentro del radio de comunicación."""

    diferencia: object
    """(N, N, 3): posición del vecino j vista desde el dron i."""

    distancia: object
    visible: object
    """(N, N): cierto si j está dentro del radio de comunicación de i."""

    n_vecinos: object
    distancia_minima: object


class Comportamientos:
    """Calcula la aceleración total que pide cada dron en un instante."""

    def __init__(self, comp: ConfigComportamiento, enjambre: ConfigEnjambre, motor: Motor):
        self.cfg = comp
        self.enjambre = enjambre
        self.motor = motor
        self.xp = motor.xp
        self._infinito = float("inf")

    # -- vecindad ----------------------------------------------------------- #

    def vecinos(self, posiciones, activo=None) -> VecindadDrones:
        xp = self.xp
        n = posiciones.shape[0]
        diferencia = posiciones[None, :, :] - posiciones[:, None, :]
        distancia = xp.linalg.norm(diferencia, axis=-1)

        propio = xp.eye(n, dtype=bool)
        visible = (distancia <= self.enjambre.r_com_m) & ~propio
        if activo is not None:
            visible = visible & activo[None, :] & activo[:, None]

        distancia_enmascarada = xp.where(visible, distancia, self._infinito)
        return VecindadDrones(
            diferencia=diferencia,
            distancia=distancia,
            visible=visible,
            n_vecinos=visible.sum(axis=1),
            distancia_minima=distancia_enmascarada.min(axis=1),
        )

    # -- comportamientos ---------------------------------------------------- #

    def hacia_puesto(self, posiciones, velocidad_suelo, puestos, v_max: float):
        """Dirigirse al puesto asignado en la formación.

        Es el comportamiento que cumple los dos papeles a la vez: como el
        puesto se mueve a lo largo de la ruta de barrido, seguirlo es cumplir
        la misión, y mantener su sitio respecto a los demás es mantener la
        formación.

        Se compara con la velocidad **sobre el terreno**, de modo que el dron
        compense por sí mismo la deriva del viento, como hace un aparato
        guiado por GPS: el viento le cuesta velocidad y batería, pero no se
        lleva la formación por delante.
        """
        xp = self.xp
        error = puestos - posiciones
        deseada = self._saturar(error * self.cfg.puesto_ganancia, v_max)
        return (deseada - velocidad_suelo) / self.enjambre.dron.tau_respuesta_s

    def evitar_obstaculos(self, velocidad_suelo, vecindad: Vecindad):
        """Campo potencial repulsivo más una componente de rodeo.

        La repulsión lleva el término 1/d² clásico: a 10 metros el obstáculo
        casi no se nota y a 1 metro empuja cien veces más fuerte, que es lo que
        garantiza que el dron no llegue a tocar (`docs/02`, §6).

        La componente tangencial es la que evita el fallo célebre de los campos
        potenciales: sin ella, un dron que va de frente contra una pared con su
        destino detrás se queda clavado, porque el empujón y la atracción se
        cancelan. Empujando además de lado, el dron **rodea** el obstáculo.
        """
        xp = self.xp
        if not vecindad.hay_candidatos:
            return xp.zeros_like(velocidad_suelo)

        d0 = self.cfg.obst_radio_influencia_m
        d = xp.maximum(vecindad.distancia, 0.05)
        dentro_de_influencia = vecindad.distancia < d0

        magnitud = self.cfg.obst_k * (1.0 / d - 1.0 / d0) / (d * d)
        magnitud = xp.where(dentro_de_influencia, magnitud, 0.0)
        # Un dron que ya ha penetrado recibe el empujón máximo, sin que la
        # división por una distancia casi nula desborde a infinito.
        techo = 50.0 * self.enjambre.dron.a_max_ms2
        magnitud = xp.minimum(magnitud, techo)
        magnitud = xp.where(vecindad.dentro, techo, magnitud)

        radial = (magnitud[..., None] * vecindad.direccion).sum(axis=1)

        # Tangente horizontal, girada 90° respecto a la dirección de empuje.
        u = vecindad.direccion
        tangente = xp.stack([-u[..., 1], u[..., 0], xp.zeros_like(u[..., 0])], axis=-1)
        norma = xp.linalg.norm(tangente, axis=-1, keepdims=True)
        tangente = tangente / xp.maximum(norma, 1e-9)
        # Se rodea por el lado hacia el que el dron ya se inclina.
        sentido = xp.sign((tangente * velocidad_suelo[:, None, :]).sum(axis=-1))
        tangencial = (
            self.cfg.obst_tangencial * magnitud * sentido
        )[..., None] * tangente

        return radial + tangencial.sum(axis=1)

    def anticolision(self, posiciones, velocidad_suelo, vecindad: VecindadDrones):
        """Anticolisión predictiva por punto de máxima aproximación.

        No basta con mirar la distancia actual: dos drones a 4 m que vuelan en
        paralelo no tienen problema, y dos a 40 m que van de frente a 15 m/s
        chocan en poco más de un segundo. Lo que informa del peligro es hacia
        dónde van (`docs/02`, §7).

            t_cpa = −(r · w) / |w|²

        La maniobra sale **recíproca sin necesidad de acordarla**: como la
        velocidad relativa que ve j es la opuesta a la que ve i, ambos escapan
        en sentidos contrarios. Cada uno hace la mitad, evitando el "baile del
        pasillo".
        """
        xp = self.xp
        r = vecindad.diferencia
        w = velocidad_suelo[None, :, :] - velocidad_suelo[:, None, :]

        w2 = (w * w).sum(axis=-1)
        rw = (r * w).sum(axis=-1)
        horizonte = self.cfg.anti_horizonte_s
        # Con velocidad relativa nula no hay aproximación: t_cpa se manda al
        # infinito para que la condición de peligro lo descarte.
        t_cpa = xp.where(w2 > 1e-9, -rw / xp.maximum(w2, 1e-9), horizonte * 10.0)
        t_cpa = xp.clip(t_cpa, 0.0, horizonte)

        cierre = r + w * t_cpa[..., None]
        d_cpa = xp.linalg.norm(cierre, axis=-1)

        d_seg = self.cfg.anti_distancia_seguridad_m
        peligro = vecindad.visible & (d_cpa < d_seg) & (rw < 0.0)

        # Escapar en sentido contrario a donde estará el vecino en el momento
        # de máxima cercanía.
        norma = xp.linalg.norm(cierre, axis=-1, keepdims=True)
        escape = -cierre / xp.maximum(norma, 1e-9)
        # Aproximación exactamente frontal: el vector de escape es nulo y hay
        # que elegir un lado. La perpendicular a la velocidad relativa da
        # lados opuestos a los dos drones automáticamente.
        perpendicular = xp.stack([-w[..., 1], w[..., 0], xp.zeros_like(w[..., 0])], axis=-1)
        perpendicular = perpendicular / xp.maximum(
            xp.linalg.norm(perpendicular, axis=-1, keepdims=True), 1e-9
        )
        escape = xp.where(norma > 1e-6, escape, perpendicular)

        urgencia_distancia = xp.clip((d_seg - d_cpa) / d_seg, 0.0, 1.0)
        urgencia_tiempo = xp.clip((horizonte - t_cpa) / horizonte, 0.0, 1.0)
        intensidad = self.cfg.anti_ganancia * urgencia_distancia * urgencia_tiempo
        intensidad = xp.where(peligro, intensidad, 0.0)
        if self.cfg.anti_reciproco:
            intensidad = intensidad * 0.5

        return (intensidad[..., None] * escape).sum(axis=1)

    def separacion(self, vecindad: VecindadDrones):
        """Repulsión de cortesía a corta distancia: la red de seguridad.

        La anticolisión predictiva resuelve los cruces; esto atrapa lo que se
        le escape, por ejemplo dos drones que ya están demasiado juntos y casi
        quietos, donde no hay aproximación que predecir.
        """
        xp = self.xp
        d_sep = self.cfg.sep_distancia_m
        d = xp.maximum(vecindad.distancia, 0.05)
        cerca = vecindad.visible & (vecindad.distancia < d_sep)

        magnitud = self.cfg.sep_k * (1.0 / d - 1.0 / d_sep) / (d * d)
        magnitud = xp.where(cerca, xp.minimum(magnitud, 50.0 * self.enjambre.dron.a_max_ms2), 0.0)

        alejarse = -vecindad.diferencia / xp.maximum(d, 1e-9)[..., None]
        return (magnitud[..., None] * alejarse).sum(axis=1)

    def cohesion(self, posiciones, vecindad: VecindadDrones):
        """Tirón hacia el enjambre cuando se supera la separación máxima.

        Implementa `d_max` como **objetivo, no como candado**: en un bosque los
        huecos entre árboles son más estrechos que la propia formación, así que
        una formación rígida no cabría. El dron rompe formación, pasa, y esta
        fuerza lo trae de vuelta (`docs/04`, §5).
        """
        xp = self.xp
        umbral = self.enjambre.formacion.separacion_max_m + self.cfg.cohesion_holgura
        desgajado = vecindad.distancia_minima > umbral

        peso = vecindad.visible.astype(posiciones.dtype)
        total = peso.sum(axis=1, keepdims=True)
        centro = (peso[..., None] * vecindad.diferencia).sum(axis=1) / xp.maximum(total, 1.0)

        norma = xp.linalg.norm(centro, axis=-1, keepdims=True)
        direccion = centro / xp.maximum(norma, 1e-9)
        exceso = xp.clip(vecindad.distancia_minima - umbral, 0.0, 50.0)
        # Sin ningún vecino a la vista no hay enjambre al que volver: de eso se
        # encarga el puesto asignado.
        aplicable = desgajado & (vecindad.n_vecinos > 0)
        return xp.where(aplicable[:, None], direccion * exceso[:, None], 0.0)

    # -- suma --------------------------------------------------------------- #

    def total(self, a_puesto, a_obstaculos, a_anticolision, a_separacion, a_cohesion):
        p = self.cfg.pesos
        return (
            p.puesto * a_puesto
            + p.obstaculos * a_obstaculos
            + p.anticolision * a_anticolision
            + p.separacion * a_separacion
            + p.cohesion * a_cohesion
        )

    def _saturar(self, vector, maximo: float):
        xp = self.xp
        norma = xp.linalg.norm(vector, axis=-1, keepdims=True)
        return vector * xp.minimum(1.0, maximo / xp.maximum(norma, 1e-12))
