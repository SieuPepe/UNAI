"""Comprobaciones de la lógica de evitación.

Los casos de aquí son los que destaparon los cuatro fallos corregidos durante
el desarrollo: el desempate nulo del término tangencial y la falta de límite de
velocidad de acercamiento. Están para que no vuelvan.
"""

import numpy as np
import pytest

from unai import entorno as E
from unai.calculo import seleccionar
from unai.comportamientos import Comportamientos
from unai.config import ConfigComportamiento, ConfigEnjambre
from unai.vuelo import ModeloCinematico


@pytest.fixture
def motor():
    return seleccionar(False)


@pytest.fixture
def comp(motor):
    return Comportamientos(ConfigComportamiento(), ConfigEnjambre(n_drones=2), motor)


def test_anticolision_es_reciproca_y_opuesta(comp):
    """Cada dron hace la mitad y hacia el lado contrario: sin eso, el baile del pasillo."""
    p = np.array([[0.0, 0.0, 5.0], [40.0, 0.0, 5.0]])
    v = np.array([[15.0, 0.0, 0.0], [-15.0, 0.0, 0.0]])
    a = comp.anticolision(p, v, comp.vecinos(p))

    assert np.linalg.norm(a[0]) > 0.1
    assert np.allclose(a[0], -a[1])
    # La corrección va de lado, no hacia atrás: frenar es lento e ineficaz.
    assert abs(a[0, 0]) < 1e-9


def test_anticolision_ignora_el_vuelo_en_paralelo(comp):
    """Dos drones a 4 m que van en paralelo no tienen ningún problema."""
    p = np.array([[0.0, 0.0, 5.0], [0.0, 4.0, 5.0]])
    v = np.array([[15.0, 0.0, 0.0], [15.0, 0.0, 0.0]])
    assert np.allclose(comp.anticolision(p, v, comp.vecinos(p)), 0.0)


def test_anticolision_ignora_a_quien_se_aleja(comp):
    p = np.array([[0.0, 0.0, 5.0], [-40.0, 0.0, 5.0]])
    v = np.array([[15.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
    assert np.allclose(comp.anticolision(p, v, comp.vecinos(p)), 0.0)


def test_dos_drones_de_frente_no_chocan(motor):
    """El caso más duro: metas cruzadas, ambos a tope, en línea recta."""
    enj = ConfigEnjambre(n_drones=2)
    comp = Comportamientos(ConfigComportamiento(), enj, motor)
    modelo = ModeloCinematico(enj.dron, motor)

    p = np.array([[0.0, 0.0, 5.0], [80.0, 0.0, 5.0]])
    v = np.array([[15.0, 0.0, 0.0], [-15.0, 0.0, 0.0]])
    metas = np.array([[180.0, 0.0, 5.0], [-100.0, 0.0, 5.0]])
    minimo = np.inf

    for _ in range(1200):
        vecinos = comp.vecinos(p)
        minimo = min(minimo, float(vecinos.distancia_minima.min()))
        a = comp.total(
            comp.hacia_puesto(p, v, metas, 15.0),
            np.zeros((2, 3)),
            comp.anticolision(p, v, vecinos),
            comp.separacion(vecinos),
            np.zeros((2, 3)),
        )
        p, v = modelo.avanzar(p, v, a, np.zeros((2, 3)), 0.02)

    assert minimo > 2.0 * enj.dron.radio_m


@pytest.mark.parametrize("desvio", [0.0, 0.15, 1.0, 3.0])
def test_un_dron_esquiva_un_arbol_de_frente(motor, desvio):
    """Aproximación perfectamente frontal.

    Es el caso que atravesaba el árbol: el término tangencial se multiplicaba
    por sign(tangente·velocidad), que vale cero justo en la simetría perfecta.
    """
    enj = ConfigEnjambre(n_drones=1)
    comp = Comportamientos(ConfigComportamiento(), enj, motor)
    modelo = ModeloCinematico(enj.dron, motor)
    campo = E.CampoObstaculos(
        np.array([[50.0, 0.0, 0.3, 0.0, 12.0]]), np.empty((0, 6)), 200.0, 200.0, 20.0, 16, motor
    )

    p = np.array([[0.0, desvio, 5.0]])
    v = np.array([[15.0, 0.0, 0.0]])
    meta = np.array([[200.0, desvio, 5.0]])
    minimo = np.inf

    for _ in range(1600):
        cercanos = campo.consultar(p)
        minimo = min(minimo, float(cercanos.distancia.min()))
        a = comp.total(
            comp.hacia_puesto(p, v, meta, 15.0, np.array([15.0, 0.0, 0.0])),
            comp.evitar_obstaculos(v, cercanos),
            np.zeros((1, 3)), np.zeros((1, 3)), np.zeros((1, 3)),
        )
        p, v = modelo.avanzar(p, v, a, np.zeros((1, 3)), 0.02)

    assert minimo > enj.dron.radio_m, "el dron ha atravesado el tronco"
    assert p[0, 0] > 150.0, "el dron no ha continuado hacia su meta"


def test_un_dron_no_se_estrella_contra_una_pared(motor):
    """Sin límite de velocidad de acercamiento, llegaba a 1,9 m con 6,7 m/s.

    Frenar eso exige 11,9 m/s² y el aparato solo tiene 9,81: a esa distancia ya
    no existe maniobra posible, por buena que sea la lógica de esquive.
    """
    enj = ConfigEnjambre(n_drones=1)
    comp = Comportamientos(ConfigComportamiento(), enj, motor)
    modelo = ModeloCinematico(enj.dron, motor)
    campo = E.CampoObstaculos(
        np.empty((0, 5)), np.array([[48.0, -40.0, 0.0, 52.0, 40.0, 15.0]]),
        200.0, 200.0, 20.0, 16, motor,
    )

    p = np.array([[0.0, 0.0, 5.0]])
    v = np.array([[15.0, 0.0, 0.0]])
    minimo = np.inf
    for _ in range(3500):
        cercanos = campo.consultar(p)
        minimo = min(minimo, float(cercanos.distancia.min()))
        a = comp.total(
            comp.hacia_puesto(p, v, np.array([[200.0, 0.0, 5.0]]), 15.0,
                              np.array([15.0, 0.0, 0.0])),
            comp.evitar_obstaculos(v, cercanos),
            np.zeros((1, 3)), np.zeros((1, 3)), np.zeros((1, 3)),
        )
        p, v = modelo.avanzar(p, v, a, np.zeros((1, 3)), 0.02)

    assert minimo > enj.dron.radio_m, "el dron ha penetrado la pared"


def test_la_cohesion_solo_tira_de_los_desgajados(motor):
    """`d_max` es un objetivo, no un candado: solo actúa al superarse."""
    enj = ConfigEnjambre(n_drones=3)
    comp = Comportamientos(ConfigComportamiento(), enj, motor)
    juntos = np.array([[0.0, 0.0, 5.0], [10.0, 0.0, 5.0], [20.0, 0.0, 5.0]])
    assert np.allclose(comp.cohesion(juntos, comp.vecinos(juntos)), 0.0)

    lejos = np.array([[0.0, 0.0, 5.0], [10.0, 0.0, 5.0], [60.0, 0.0, 5.0]])
    fuerza = comp.cohesion(lejos, comp.vecinos(lejos))
    assert np.linalg.norm(fuerza[2]) > 0.0
    assert fuerza[2][0] < 0.0, "debería tirar del rezagado hacia el enjambre"


def test_el_radio_de_comunicacion_limita_lo_que_se_ve(motor):
    """Conocimiento local: cada dron solo ve a los vecinos cercanos."""
    enj = ConfigEnjambre(n_drones=3, r_com_m=15.0)
    comp = Comportamientos(ConfigComportamiento(), enj, motor)
    p = np.array([[0.0, 0.0, 5.0], [10.0, 0.0, 5.0], [100.0, 0.0, 5.0]])
    vecinos = comp.vecinos(p)
    assert vecinos.n_vecinos.tolist() == [1, 1, 0]
    assert not vecinos.visible[0, 2]
