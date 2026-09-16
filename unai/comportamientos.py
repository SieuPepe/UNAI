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


def _norma(xp, v):
    """Norma por la última dimensión.

    `linalg.norm` es genérica y valida ejes y órdenes en cada llamada; sobre
    matrices de pares (N, N, 3) llamadas cincuenta veces por segundo simulado,
    ese sobrecoste se nota.
    """
    return xp.sqrt((v * v).sum(axis=-1))


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
        distancia = _norma(xp, diferencia)

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

    def hacia_puesto(
        self, posiciones, velocidad_suelo, puestos, v_max: float, velocidad_puesto=None
    ):
        """Dirigirse al puesto asignado en la formación.

        Es el comportamiento que cumple los dos papeles a la vez: como el
        puesto se mueve a lo largo de la ruta de barrido, seguirlo es cumplir
        la misión, y mantener su sitio respecto a los demás es mantener la
        formación.

        Se compara con la velocidad **sobre el terreno**, de modo que el dron
        compense por sí mismo la deriva del viento, como hace un aparato
        guiado por GPS: el viento le cuesta velocidad y batería, pero no se
        lleva la formación por delante.

        `velocidad_puesto` es el término anticipativo: la velocidad a la que se
        mueve el propio puesto. Sin él, el dron solo aceleraría cuando ya va
        retrasado y el retraso se volvería permanente.
        """
        xp = self.xp
        error = puestos - posiciones
        deseada = error * self.cfg.puesto_ganancia
        if velocidad_puesto is not None:
            deseada = deseada + xp.asarray(velocidad_puesto)[None, :]
        deseada = self._saturar(deseada, v_max)
        return (deseada - velocidad_suelo) / self.enjambre.dron.tau_respuesta_s

    def evitar_obstaculos(self, velocidad_suelo, vecindad: Vecindad):
        """Esquive predictivo de obstáculos, con campo potencial de reserva.

        Dos mecanismos superpuestos:

        1. **Esquive por tiempo hasta el impacto.** Se mide a qué velocidad se
           acerca el dron a la superficie del obstáculo y cuánto tardaría en
           alcanzarla; si falta menos que el horizonte, se aplica una
           aceleración lateral que crece con la urgencia. Es lo que hace que el
           dron empiece a rodear el árbol treinta metros antes y no encima.

        2. **Barrera de campo potencial.** El clásico término 1/d², que a diez
           metros casi no se nota y a un metro empuja cien veces más fuerte
           (`docs/02`, §6). Es la última defensa, no el mecanismo principal:
           por sí solo es demasiado débil de lejos y demasiado brusco de cerca
           para un dron que va a 15 m/s.

        El lado por el que se rodea es aquel hacia el que el dron ya se inclina.
        En una aproximación perfectamente frontal ese lado no existe —la
        proyección vale cero— y es justo el caso que deja al dron clavado
        contra el obstáculo o lo hace atravesarlo. El empate se rompe con un
        lado fijo, la misma regla que usan los barcos al cruzarse de frente.
        """
        xp = self.xp
        if not vecindad.hay_candidatos:
            return xp.zeros_like(velocidad_suelo)

        d0 = self.cfg.obst_radio_influencia_m
        u = vecindad.direccion
        d = xp.maximum(vecindad.distancia, 0.05)
        en_influencia = vecindad.distancia < d0

        # Tangente horizontal y lado de rodeo.
        tangente = xp.stack([-u[..., 1], u[..., 0], xp.zeros_like(u[..., 0])], axis=-1)
        tangente = tangente / xp.maximum(_norma(xp, tangente), 1e-9)[..., None]
        proyeccion = (tangente * velocidad_suelo[:, None, :]).sum(axis=-1)
        sentido = xp.where(xp.abs(proyeccion) > 0.1, xp.sign(proyeccion), 1.0)

        # 1) Esquive predictivo.
        cierre = -(u * velocidad_suelo[:, None, :]).sum(axis=-1)
        horizonte = self.cfg.obst_horizonte_s
        t_impacto = d / xp.maximum(cierre, 0.1)
        inminente = en_influencia & (cierre > 0.1) & (t_impacto < horizonte)
        urgencia = xp.where(inminente, 1.0 - t_impacto / horizonte, 0.0)

        lateral = (self.cfg.obst_ganancia_lateral * urgencia * sentido)[..., None] * tangente
        frenado = (
            self.cfg.obst_ganancia_lateral * self.cfg.obst_ganancia_frenado * urgencia
        )[..., None] * u

        # Límite de velocidad de acercamiento por distancia de frenado. Es la
        # condición que hace la evitación físicamente realizable: sin ella el
        # dron gasta su aceleración en apartarse de lado, llega a metro y medio
        # de la pared con siete metros por segundo hacia ella, y en ese punto
        # ninguna lógica de esquive puede ya salvarlo porque no existe la
        # aceleración necesaria.
        a_freno = self.cfg.obst_freno_fraccion * self.enjambre.dron.a_max_ms2
        margen = xp.maximum(d - self.cfg.obst_margen_m - self.enjambre.dron.radio_m, 0.0)
        permitida = xp.sqrt(2.0 * a_freno * margen)
        exceso = xp.where(en_influencia, xp.maximum(cierre - permitida, 0.0), 0.0)
        freno_duro = (self.cfg.obst_ganancia_freno * exceso)[..., None] * u

        # 2) Barrera de campo potencial.
        magnitud = self.cfg.obst_k * (1.0 / d - 1.0 / d0) / (d * d)
        techo = 50.0 * self.enjambre.dron.a_max_ms2
        magnitud = xp.where(en_influencia, xp.minimum(magnitud, techo), 0.0)
        magnitud = xp.where(vecindad.dentro, techo, magnitud)
        barrera = magnitud[..., None] * (
            u + (self.cfg.obst_tangencial * sentido)[..., None] * tangente
        )

        return (lateral + frenado + freno_duro + barrera).sum(axis=1)

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
        # Con velocidad relativa nula no hay aproximación, y con rw >= 0 los
        # drones ya se están separando: en ambos casos t_cpa queda en cero y
        # la condición de peligro los descarta.
        t_cpa = xp.minimum(xp.maximum(-rw / xp.maximum(w2, 1e-9), 0.0), horizonte)

        cierre = r + w * t_cpa[..., None]
        d_cpa2 = (cierre * cierre).sum(axis=-1)

        d_seg = self.cfg.anti_distancia_seguridad_m
        peligro = vecindad.visible & (d_cpa2 < d_seg * d_seg) & (rw < 0.0)

        # Escapar en sentido contrario a donde estará el vecino en el momento
        # de máxima cercanía. En una aproximación exactamente frontal ese
        # vector es nulo y hay que elegir un lado: la perpendicular a la
        # velocidad relativa da lados opuestos a los dos drones de forma
        # automática, porque cada uno ve la velocidad relativa del otro con el
        # signo cambiado. La reciprocidad sale sola, sin acordarla.
        perpendicular = xp.stack([-w[..., 1], w[..., 0], xp.zeros_like(w[..., 0])], axis=-1)
        bruto = xp.where(d_cpa2[..., None] > 1e-12, -cierre, perpendicular)
        escape = bruto / xp.maximum(_norma(xp, bruto), 1e-9)[..., None]

        d_cpa = xp.sqrt(d_cpa2)
        urgencia = ((d_seg - d_cpa) / d_seg) * ((horizonte - t_cpa) / horizonte)
        intensidad = xp.where(peligro, self.cfg.anti_ganancia * urgencia, 0.0)
        if self.cfg.anti_reciproco:
            intensidad = intensidad * 0.5

        # Límite de velocidad de acercamiento por distancia de frenado, igual
        # que frente a los obstáculos. La lógica anterior decide hacia dónde
        # apartarse; esta impide llegar a una distancia desde la que apartarse
        # ya no sea físicamente posible.
        d = xp.maximum(vecindad.distancia, 1e-6)
        hacia = r / d[..., None]
        cierre_radial = -rw / d
        holgura = xp.maximum(
            d - 2.0 * self.enjambre.dron.radio_m - self.cfg.anti_margen_m, 0.0
        )
        # Frenan los dos a la vez, así que la deceleración efectiva es doble.
        a_freno = 2.0 * self.cfg.anti_freno_fraccion * self.enjambre.dron.a_max_ms2
        exceso = xp.where(
            vecindad.visible, xp.maximum(cierre_radial - xp.sqrt(2.0 * a_freno * holgura), 0.0), 0.0
        )
        freno = (self.cfg.anti_ganancia_freno * exceso)[..., None] * (-hacia)

        return ((intensidad[..., None] * escape) + freno).sum(axis=1)

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

        alejarse = -vecindad.diferencia / d[..., None]
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

        direccion = centro / xp.maximum(_norma(xp, centro), 1e-9)[..., None]
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
        norma = _norma(xp, vector)[..., None]
        return vector * xp.minimum(1.0, maximo / xp.maximum(norma, 1e-12))
