"""Comprobaciones sobre misiones completas.

Se usan escenarios pequeños para que la batería siga siendo rápida; los
invariantes que verifican no dependen del tamaño.
"""

import warnings
from dataclasses import replace

import numpy as np
import pytest

from unai.config import (Config, ConfigEntorno, ConfigFormacion, ConfigSimulacion,
                         ConfigViento)
from unai.simulacion import simular


def config_pequena(**cambios) -> Config:
    """Nueve drones sobre 300 m: misión completa en unos segundos de reloj."""
    base = Config(
        nombre="prueba",
        entorno=ConfigEntorno(tipo="campo", lado_x_m=300.0, lado_y_m=300.0, semilla=1),
        simulacion=ConfigSimulacion(duracion_max_s=300.0, semilla=1, celda_cobertura_m=2.5),
    )
    base = replace(
        base,
        enjambre=replace(
            base.enjambre, n_drones=9,
            formacion=ConfigFormacion("linea", separacion_max_m=10.0),
        ),
    )
    for clave, valor in cambios.items():
        base = replace(base, **{clave: valor})
    return base


@pytest.fixture(scope="module")
def resultado():
    return simular(config_pequena())


def test_la_mision_se_completa(resultado):
    assert resultado.resumen["eficacia"]["motivo_fin"] == "ruta de barrido completada"
    assert resultado.resumen["eficacia"]["progreso_ruta_pct"] == pytest.approx(100.0)


def test_en_campo_abierto_no_hay_colisiones(resultado):
    assert resultado.resumen["seguridad"]["colisiones_entre_drones"] == 0
    assert resultado.resumen["seguridad"]["colisiones_con_entorno"] == 0


def test_la_formacion_se_mantiene_en_vuelo_recto(resultado):
    """Con guiado anticipativo el error en crucero es de centímetros.

    Se mide la mediana y no la media porque la media la domina el giro: en el
    vértice el enjambre se pasa de largo por fuerza, ya que revertir 15 m/s con
    9,81 m/s² de aceleración cuesta v²/2a = 11,5 metros. Eso es física, no un
    fallo de control, y por eso el máximo se acota con ese número.
    """
    serie = np.array(resultado.serie.error_formacion)
    assert np.median(serie) < 1.0
    assert serie.max() < 12.0
    assert resultado.resumen["seguridad"]["separacion_minima_m"] == pytest.approx(10.0, abs=0.5)


def test_la_zona_queda_reconocida(resultado):
    assert resultado.resumen["eficacia"]["cobertura_final_pct"] > 97.0


def test_la_cobertura_nunca_retrocede(resultado):
    serie = np.array(resultado.serie.cobertura)
    assert np.all(np.diff(serie) >= -1e-9)


def test_la_energia_crece_y_nunca_es_negativa(resultado):
    energia = np.array(resultado.serie.energia_wh)
    assert energia[0] >= 0.0
    assert np.all(np.diff(energia) >= -1e-9)
    assert resultado.resumen["coste"]["energia_total_wh"] > 0.0


def test_ningun_dron_sale_del_espacio_aereo(resultado):
    posiciones = resultado.registro.descuantizar()
    limite = resultado.config.entorno
    assert posiciones[:, :, 2].min() >= limite.altura_min_m - 0.05
    assert posiciones[:, :, 2].max() <= limite.altura_max_m + 0.05


def test_misma_semilla_mismo_resultado():
    """Sin reproducibilidad, comparar configuraciones no significa nada."""
    a = simular(config_pequena())
    b = simular(config_pequena())
    assert np.array_equal(a.registro.datos(), b.registro.datos())
    assert a.resumen == b.resumen


def test_semillas_distintas_dan_vientos_distintos():
    viento = ConfigViento(velocidad_media_ms=6.0, turbulencia_sigma_ms=2.0)
    a = simular(config_pequena(entorno=replace(
        config_pequena().entorno, viento=viento, semilla=1)))
    b = simular(config_pequena(
        entorno=replace(config_pequena().entorno, viento=viento, semilla=1),
        simulacion=replace(config_pequena().simulacion, semilla=2)))
    assert not np.array_equal(a.registro.datos(), b.registro.datos())


def test_el_viento_cuesta_energia():
    """Volar contra el viento gasta como si se fuera más rápido."""
    sin_viento = simular(config_pequena())
    con_viento = simular(config_pequena(entorno=replace(
        config_pequena().entorno,
        viento=ConfigViento(velocidad_media_ms=8.0, altura_referencia_m=5.0))))
    assert (
        con_viento.resumen["coste"]["energia_total_wh"]
        > sin_viento.resumen["coste"]["energia_total_wh"]
    )


def test_pedir_gpu_sin_gpu_avisa_y_sigue_en_cpu():
    """Un respaldo silencioso haría mentir a una comparación de rendimiento."""
    from unai.calculo import gpu_disponible

    if gpu_disponible()[0]:
        pytest.skip("hay GPU disponible: este caso no aplica")

    cfg = config_pequena(simulacion=replace(
        config_pequena().simulacion, usar_gpu=True, duracion_max_s=20.0))
    with pytest.warns(RuntimeWarning, match="GPU"):
        resultado = simular(cfg)
    assert resultado.info["dispositivo"] == "cpu"
    assert resultado.info["gpu_solicitada"] is True


def test_el_visor_es_un_fichero_autonomo(resultado, tmp_path):
    from unai.visor import generar

    ruta = generar(resultado, tmp_path / "visor.html")
    texto = ruta.read_text(encoding="utf-8")
    assert ruta.stat().st_size > 10_000
    assert "<canvas" in texto
    # Ninguna dependencia externa: se abre sin internet.
    assert "http://" not in texto and "https://" not in texto
    assert "/*__DATOS__*/" not in texto


def test_una_formacion_mas_ancha_barre_en_menos_tiempo():
    """El resultado central del proyecto: la forma decide el tiempo de misión."""
    ancha = simular(config_pequena())
    estrecha = simular(config_pequena(enjambre=replace(
        config_pequena().enjambre,
        formacion=ConfigFormacion("rejilla", columnas=3, filas=3, separacion_max_m=10.0))))

    assert (
        ancha.resumen["eficacia"]["tiempo_mision_s"]
        < estrecha.resumen["eficacia"]["tiempo_mision_s"]
    )


def test_el_reparto_entre_hilos_no_altera_el_resultado():
    """Repartir el paso entre hilos debe ser transparente.

    Cada dron se calcula con las mismas operaciones y en el mismo orden; los
    bloques solo se concatenan. Si esto fallara, la reproducibilidad —sobre la
    que descansa toda comparación de configuraciones— se vendría abajo.
    """
    uno = simular(config_pequena(simulacion=replace(
        config_pequena().simulacion, hilos=1)))
    varios = simular(config_pequena(simulacion=replace(
        config_pequena().simulacion, hilos=4)))

    assert uno.info["hilos"] == 1
    assert varios.info["hilos"] == 4
    assert np.array_equal(uno.registro.datos(), varios.registro.datos())
    assert uno.resumen == varios.resumen


def test_los_hilos_automaticos_se_ajustan_al_enjambre():
    """Con enjambres pequeños no se reparte: costaría más de lo que ahorra."""
    import os

    from unai.calculo import seleccionar
    from unai.comportamientos import Comportamientos
    from unai.config import ConfigComportamiento, ConfigEnjambre

    motor = seleccionar(False)
    nucleos = os.cpu_count() or 1

    def hilos(n):
        comp = Comportamientos(
            ConfigComportamiento(), ConfigEnjambre(n_drones=n), motor, 0
        )
        resultado = comp.hilos
        comp.cerrar()
        return resultado

    assert hilos(20) == 1
    assert hilos(100) == min(2, nucleos)
    assert hilos(100_000) == nucleos

    # Nunca más hilos que drones, ni aunque se pidan a mano.
    comp = Comportamientos(ConfigComportamiento(), ConfigEnjambre(n_drones=3), motor, 64)
    assert comp.hilos <= 3
    comp.cerrar()


def test_el_bloque_de_filas_da_lo_mismo_que_la_matriz_entera():
    """Las fuerzas de pares calculadas por bloques son idénticas a las de golpe."""
    from unai.calculo import seleccionar
    from unai.comportamientos import Comportamientos
    from unai.config import ConfigComportamiento, ConfigEnjambre

    motor = seleccionar(False)
    enjambre = ConfigEnjambre(n_drones=60)
    comp = Comportamientos(ConfigComportamiento(), enjambre, motor, 1)
    azar = np.random.default_rng(0)
    p = azar.uniform(0, 120, (60, 3))
    v = azar.uniform(-15, 15, (60, 3))

    entera = comp.vecinos(p)
    esperado = (
        comp.anticolision(p, v, entera),
        comp.separacion(entera),
        comp.cohesion(p, entera),
        entera.distancia_minima,
        entera.n_vecinos,
    )

    trozos = [comp._bloque(p, v, None, slice(i, min(i + 17, 60))) for i in range(0, 60, 17)]
    obtenido = tuple(np.concatenate([t[k] for t in trozos]) for k in range(5))

    for referencia, calculado in zip(esperado, obtenido):
        assert np.array_equal(referencia, calculado)
    comp.cerrar()
