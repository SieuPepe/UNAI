"""Geometría de los obstáculos y medición de la cobertura."""

import math

import numpy as np
import pytest

from unai import entorno as E
from unai.calculo import seleccionar
from unai.cobertura import MallaCobertura, RutaBarrido
from unai.config import ConfigDron, ConfigEntorno, ConfigFormacion
from unai.formacion import Formacion


@pytest.fixture
def motor():
    return seleccionar(False)


def test_distancia_a_un_cilindro(motor):
    campo = E.CampoObstaculos(
        np.array([[0.0, 0.0, 2.0, 0.0, 10.0]]), np.empty((0, 6)), 100.0, 100.0, 20.0, 16, motor
    )
    puntos = np.array([[10.0, 0.0, 5.0], [0.0, 5.0, 5.0], [0.0, 0.0, 5.0]])
    v = campo.consultar(puntos)

    assert v.distancia[0, 0] == pytest.approx(8.0)     # 10 − radio 2
    assert v.distancia[1, 0] == pytest.approx(3.0)
    assert v.dentro[2, 0], "un punto en el eje está dentro del tronco"
    assert np.allclose(np.linalg.norm(v.direccion, axis=-1), 1.0)
    # El empujón apunta del obstáculo hacia el dron.
    assert v.direccion[0, 0, 0] == pytest.approx(1.0)


def test_distancia_a_una_caja(motor):
    campo = E.CampoObstaculos(
        np.empty((0, 5)), np.array([[0.0, 0.0, 0.0, 10.0, 10.0, 20.0]]),
        100.0, 100.0, 20.0, 16, motor,
    )
    puntos = np.array([[15.0, 5.0, 5.0], [5.0, 5.0, 5.0], [13.0, 14.0, 5.0]])
    v = campo.consultar(puntos)

    assert v.distancia[0, 0] == pytest.approx(5.0)
    assert v.dentro[1, 0]
    assert v.distancia[2, 0] == pytest.approx(5.0)     # esquina: 3-4-5


def test_la_rejilla_no_descarta_obstaculos(motor):
    """Las plazas por celda se dimensionan con la celda más poblada."""
    azar = np.random.default_rng(0)
    n = 4000
    cil = np.column_stack([
        azar.uniform(0, 300, n), azar.uniform(0, 300, n),
        np.full(n, 0.3), np.zeros(n), np.full(n, 10.0),
    ])
    campo = E.CampoObstaculos(cil, np.empty((0, 6)), 300.0, 300.0, 20.0, 64, motor)

    puntos = np.column_stack([
        azar.uniform(30, 270, 200), azar.uniform(30, 270, 200), np.full(200, 5.0)
    ])
    por_rejilla = campo.consultar(puntos).distancia.min(axis=1)
    # Fuerza bruta contra los 4.000 troncos. Se recorta a cero porque la
    # consulta devuelve distancia nula al dron que está dentro de un tronco
    # (y lo señala con `dentro`), mientras que la resta directa daría negativo.
    dxy = np.linalg.norm(puntos[:, None, :2] - cil[None, :, :2], axis=-1) - cil[None, :, 2]
    assert np.allclose(por_rejilla, np.maximum(dxy.min(axis=1), 0.0), atol=1e-9)


@pytest.mark.parametrize("tipo", ConfigEntorno.TIPOS)
def test_los_entornos_son_reproducibles(tipo, motor):
    """Misma semilla, mismo escenario: sin esto comparar no significa nada."""
    cfg = ConfigEntorno(tipo=tipo, lado_x_m=400.0, lado_y_m=400.0, altura_max_m=60.0, semilla=7)
    a = E.construir(cfg, 20.0, motor=motor)
    b = E.construir(cfg, 20.0, motor=motor)
    assert np.array_equal(a.cilindros, b.cilindros)
    assert np.array_equal(a.cajas, b.cajas)

    otra = E.construir(
        ConfigEntorno(tipo=tipo, lado_x_m=400.0, lado_y_m=400.0, altura_max_m=60.0, semilla=8),
        20.0, motor=motor,
    )
    if tipo in ("bosque", "urbano"):
        assert not np.array_equal(a.cilindros, otra.cilindros) or not np.array_equal(
            a.cajas, otra.cajas
        )


def test_la_cobertura_mide_la_huella_real(motor):
    """Sin sesgo: la plantilla fija sobrestimaba la superficie un 59 %."""
    cfg = ConfigEntorno(tipo="campo", lado_x_m=200.0, lado_y_m=200.0)
    azar = np.random.default_rng(0)
    radio = 5.0
    medidas = []
    for _ in range(120):
        malla = MallaCobertura(cfg, 2.5, radio, motor)
        malla.marcar(np.array([[azar.uniform(50, 150), azar.uniform(50, 150), 5.0]]), 0)
        medidas.append(malla.visitadas * 2.5**2)

    assert np.mean(medidas) == pytest.approx(math.pi * radio**2, rel=0.06)


def test_una_franja_barrida_queda_cubierta_del_todo(motor):
    cfg = ConfigEntorno(tipo="campo", lado_x_m=100.0, lado_y_m=20.0)
    malla = MallaCobertura(cfg, 2.5, 5.0, motor)
    for k, x in enumerate(np.arange(0, 100, 0.3)):
        malla.marcar(np.array([[x, 5.0, 5.0], [x, 15.0, 5.0]]), k)
    assert malla.porcentaje == pytest.approx(100.0)


def test_la_cobertura_guarda_el_instante_de_la_primera_visita(motor):
    cfg = ConfigEntorno(tipo="campo", lado_x_m=50.0, lado_y_m=50.0)
    malla = MallaCobertura(cfg, 2.5, 5.0, motor)
    punto = np.array([[25.0, 25.0, 5.0]])
    malla.marcar(punto, 10)
    malla.marcar(punto, 99)
    visitadas = malla.a_numpy()
    assert visitadas[visitadas >= 0].max() == 10


@pytest.mark.parametrize(
    "forma,columnas,frente,pasadas",
    [("linea", None, 990.0, 4), ("rejilla", 50, 490.0, 7), ("rejilla", 10, 90.0, 32)],
)
def test_frente_y_pasadas_segun_la_formacion(motor, forma, columnas, frente, pasadas):
    """Los números de la tabla del docs/04, §4: de 17 minutos a casi 5 horas."""
    dron = ConfigDron()
    altura = dron.altura_sin_solape_m(10.0)
    cfg_form = ConfigFormacion(forma, columnas=columnas, filas=100 // (columnas or 100))
    formacion = Formacion(cfg_form, 100, altura, motor)
    assert formacion.frente_m == pytest.approx(frente)

    ruta = RutaBarrido(ConfigEntorno(tipo="campo"), formacion, dron.huella_m(altura), 15.0)
    assert ruta.n_pasadas == pasadas


def test_el_giro_es_en_espejo(motor):
    """La formación no rota: invierte el sentido de avance."""
    formacion = Formacion(ConfigFormacion("cuna"), 9, 5.0, motor)
    ruta = RutaBarrido(ConfigEntorno(tipo="campo"), formacion, 10.0, 15.0)
    assert ruta.sentido == 1.0

    ida = formacion.en_mundo(np.array([0.0, 0.0, 5.0]), 1.0)
    vuelta = formacion.en_mundo(np.array([0.0, 0.0, 5.0]), -1.0)
    assert np.allclose(ida[:, 0], -vuelta[:, 0])
    assert np.allclose(ida[:, 1], vuelta[:, 1])

    for _ in range(int(280 / 0.02)):
        ruta.avanzar(0.02, 0.0)
    assert ruta.sentido == -1.0


def test_el_guia_frena_si_el_enjambre_se_retrasa(motor):
    """Sin esto, la ruta se completaría con los drones a kilómetros."""
    formacion = Formacion(ConfigFormacion("linea"), 100, 5.0, motor)
    ruta_libre = RutaBarrido(ConfigEntorno(tipo="campo"), formacion, 10.0, 15.0)
    ruta_frenada = RutaBarrido(ConfigEntorno(tipo="campo"), formacion, 10.0, 15.0)

    for _ in range(100):
        ruta_libre.avanzar(0.02, 0.0)
        ruta_frenada.avanzar(0.02, ruta_frenada.tolerancia * 0.5)

    assert ruta_frenada.recorrido_m == pytest.approx(ruta_libre.recorrido_m * 0.5, rel=1e-6)

    parada = RutaBarrido(ConfigEntorno(tipo="campo"), formacion, 10.0, 15.0)
    for _ in range(100):
        parada.avanzar(0.02, parada.tolerancia * 5.0)
    assert parada.recorrido_m == 0.0
