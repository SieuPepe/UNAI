"""Comprobaciones de los invariantes físicos.

Son las verificaciones automáticas del principio 4 de `docs/01`: ningún dron
supera su velocidad máxima, ninguno atraviesa un obstáculo, la energía nunca es
negativa. Sin esto, el proyecto se rompe en silencio según crece.
"""

import math

import numpy as np
import pytest

from unai import entorno as E
from unai.calculo import seleccionar
from unai.comportamientos import Comportamientos
from unai.config import (Config, ConfigComportamiento, ConfigDron, ConfigEnjambre,
                         ConfigFormacion, ConfigSimulacion, ConfigViento)
from unai.viento import Viento
from unai.vuelo import ModeloCinematico


@pytest.fixture
def motor():
    return seleccionar(False)


def test_saturacion_conserva_la_direccion(motor):
    """Truncar por ejes deformaría la dirección: se recorta la longitud."""
    cfg = ConfigDron()
    modelo = ModeloCinematico(cfg, motor)
    a = np.array([[100.0, 100.0, 100.0], [0.0, -500.0, 0.0]])
    saturada = modelo._saturar(a, cfg.a_max_ms2)

    assert np.allclose(np.linalg.norm(saturada, axis=1), cfg.a_max_ms2)
    for original, recortada in zip(a, saturada):
        coseno = original @ recortada / (np.linalg.norm(original) * np.linalg.norm(recortada))
        assert coseno == pytest.approx(1.0)


def test_nunca_se_supera_la_velocidad_maxima(motor):
    cfg = ConfigDron()
    modelo = ModeloCinematico(cfg, motor)
    azar = np.random.default_rng(0)
    p = azar.uniform(0, 100, (50, 3))
    v = np.zeros((50, 3))

    for _ in range(400):
        a = azar.uniform(-200, 200, (50, 3))
        p, v = modelo.avanzar(p, v, a, np.zeros((50, 3)), 0.02)
        assert np.all(np.linalg.norm(v[:, :2], axis=1) <= cfg.v_max_horizontal_ms + 1e-9)
        assert np.all(v[:, 2] <= cfg.v_max_ascenso_ms + 1e-9)
        assert np.all(v[:, 2] >= -cfg.v_max_descenso_ms - 1e-9)


def test_el_giro_esta_limitado(motor):
    """Un dron no cambia de rumbo al instante."""
    cfg = ConfigDron(giro_max_rad_s=1.0)
    modelo = ModeloCinematico(cfg, motor)
    dt = 0.02
    v0 = np.array([[10.0, 0.0, 0.0]])
    # Aceleración lateral brutal: el límite de giro debe contenerla.
    _, v1 = modelo.avanzar(np.zeros((1, 3)), v0, np.array([[0.0, 1e4, 0.0]]),
                           np.zeros((1, 3)), dt)
    giro = abs(math.atan2(v1[0, 1], v1[0, 0]))
    assert giro <= cfg.giro_max_rad_s * dt + 1e-9


def test_el_viento_desplaza_sobre_el_terreno(motor):
    """v_suelo = v_aire + v_viento: de ahí sale que volar contra el viento cueste."""
    modelo = ModeloCinematico(ConfigDron(), motor)
    p = np.zeros((1, 3))
    v = np.array([[10.0, 0.0, 0.0]])
    viento = np.array([[-4.0, 0.0, 0.0]])
    p2, _ = modelo.avanzar(p, v, np.zeros((1, 3)), viento, 1.0)
    assert p2[0, 0] == pytest.approx(6.0, abs=1e-6)


def test_turbulencia_sigue_a_ornstein_uhlenbeck(motor):
    """Ruido con memoria: sigma estacionaria y autocorrelación exp(-t/T)."""
    cfg = ConfigViento(turbulencia_sigma_ms=2.0, tiempo_correlacion_s=5.0)
    viento = Viento(cfg, motor, semilla=1)
    muestras = np.empty(200_000)
    for i in range(muestras.size):
        viento.avanzar(0.02)
        muestras[i] = viento.rafaga_actual[0]
    muestras = muestras[5000:]

    assert muestras.std() == pytest.approx(2.0, rel=0.12)
    retardo = int(5.0 / 0.02)
    correlacion = np.corrcoef(muestras[:-retardo], muestras[retardo:])[0, 1]
    assert correlacion == pytest.approx(math.exp(-1.0), abs=0.12)


def test_perfil_de_viento_con_la_altura(motor):
    """Ley de potencia: el rozamiento con el terreno frena el viento abajo."""
    cfg = ConfigViento(velocidad_media_ms=8.0, altura_referencia_m=10.0, exponente_alfa=0.14)
    viento = Viento(cfg, motor, semilla=0)
    alturas = np.array([2.0, 10.0, 50.0])
    medido = np.linalg.norm(viento.en(np.column_stack([np.zeros(3), np.zeros(3), alturas])), axis=1)
    esperado = 8.0 * (alturas / 10.0) ** 0.14
    assert np.allclose(medido, esperado)
