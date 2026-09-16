"""Configuración, registro de trayectorias y estimación previa."""

import json
import math
import warnings
from dataclasses import replace

import numpy as np
import pytest

from unai.calculo import seleccionar
from unai.config import Config, ConfigEnjambre, ConfigFormacion
from unai.estimacion import resumen_previo
from unai.registro import RegistroTrayectorias


def test_ida_y_vuelta_de_la_configuracion(tmp_path):
    cfg = Config().validar()
    ruta = tmp_path / "config.json"
    cfg.guardar(ruta)
    assert Config.desde_fichero(ruta) == cfg


def test_una_clave_mal_escrita_no_pasa_en_silencio():
    """Ignorarla daría un resultado distinto del esperado sin decir por qué."""
    with pytest.raises(ValueError, match="n_drons"):
        Config.desde_dict({"enjambre": {"n_drons": 10}})


def test_la_altura_se_deriva_de_la_separacion():
    """Acople altura-separación: con 10 m de separación, la altura son 5 m."""
    cfg = Config()
    assert cfg.enjambre.altura_vuelo_m == pytest.approx(5.0)
    assert cfg.enjambre.dron.huella_m(5.0) == pytest.approx(10.0)

    cfg30 = replace(
        cfg,
        enjambre=replace(
            cfg.enjambre, formacion=replace(cfg.enjambre.formacion, separacion_max_m=30.0)
        ),
    )
    assert cfg30.enjambre.altura_vuelo_m == pytest.approx(15.0)


def test_avisa_si_el_radio_de_comunicacion_se_queda_corto():
    """Un radio menor no da un enjambre más local: da un horizonte más corto."""
    cfg = Config()
    corto = replace(cfg, enjambre=replace(cfg.enjambre, r_com_m=30.0))
    with pytest.warns(RuntimeWarning, match="horizonte"):
        corto.validar()


def test_la_altura_debe_caber_en_el_espacio_aereo():
    cfg = Config()
    alto = replace(
        cfg,
        enjambre=replace(
            cfg.enjambre, formacion=replace(cfg.enjambre.formacion, altura_m=500.0)
        ),
    )
    with pytest.raises(ValueError, match="espacio aéreo"):
        alto.validar()


def test_la_rejilla_debe_dar_cabida_a_todos():
    with pytest.raises(ValueError, match="cabida"):
        ConfigEnjambre(n_drones=100, formacion=ConfigFormacion("rejilla", columnas=5, filas=5)
                       ).validar()


def test_error_de_cuantizacion_por_debajo_de_cinco_centimetros():
    """Sobre 3.162 m, 16 bits dan 4,8 cm: muy por encima de lo que pide un dibujo."""
    motor = seleccionar(False)
    registro = RegistroTrayectorias(motor, [0.0, 0.0, 0.0], [3162.0, 3162.0, 120.0])
    azar = np.random.default_rng(0)
    originales = []
    for k in range(50):
        p = np.column_stack([
            azar.uniform(0, 3162, 100), azar.uniform(0, 3162, 100), azar.uniform(0, 120, 100)
        ])
        originales.append(p)
        registro.anotar(k * 0.2, p)

    error = np.abs(np.stack(originales) - registro.descuantizar())
    assert error.max() < 0.05
    assert registro.n_marcos == 50


def test_el_tamano_del_visor_es_el_previsto():
    """Una misión de 17 min a 5 Hz con 100 drones son 3,1 MB (`docs/04`, §9)."""
    marcos = 17 * 60 * 5
    assert marcos * 100 * 3 * 2 / 1e6 == pytest.approx(3.06, abs=0.1)


@pytest.mark.parametrize(
    "forma,columnas,frente,pasadas",
    [("linea", None, 990.0, 4), ("rejilla", 50, 490.0, 7), ("rejilla", 10, 90.0, 32)],
)
def test_la_estimacion_previa_coincide_con_la_simulacion(forma, columnas, frente, pasadas):
    """Lo que la ventana anuncia antes de lanzar debe ser lo que luego ocurre."""
    cfg = Config()
    formacion = ConfigFormacion(forma, columnas=columnas, filas=100 // (columnas or 100))
    cfg = replace(cfg, enjambre=replace(cfg.enjambre, formacion=formacion))
    datos = resumen_previo(cfg)
    assert datos["frente_m"] == pytest.approx(frente)
    assert datos["pasadas"] == pasadas


def test_la_estimacion_avisa_de_la_redundancia_por_volar_alto():
    """A 50 m de altura cada punto lo miran cien drones a la vez."""
    cfg = Config()
    cfg = replace(
        cfg,
        enjambre=replace(
            cfg.enjambre, formacion=replace(cfg.enjambre.formacion, altura_m=50.0)
        ),
    )
    datos = resumen_previo(cfg)
    assert datos["redundancia"] == pytest.approx(100.0)
    assert any("miran" in a for a in datos["avisos"])
