"""El bucle principal: lo que se ejecuta 50 veces por segundo de vuelo simulado.

Sigue paso por paso el ciclo descrito en `docs/02`, §13. Cada pieza —modelo de
vuelo, comportamientos, entorno, métricas, registro— es sustituible sin tocar
las demás (`docs/01`, §6.3).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from . import entorno as mod_entorno
from .calculo import Motor, seleccionar
from .cobertura import MallaCobertura, RutaBarrido
from .comportamientos import Comportamientos
from .config import Config
from .formacion import Formacion
from .metricas import Metricas, SerieTemporal
from .registro import RegistroTrayectorias
from .viento import Viento
from .vuelo import ModeloCinematico


@dataclass
class Resultado:
    """Todo lo que produce una ejecución."""

    config: Config
    resumen: dict
    serie: SerieTemporal
    registro: RegistroTrayectorias
    cobertura: np.ndarray
    obstaculos: dict
    info: dict = field(default_factory=dict)


def simular(
    cfg: Config,
    motor: Motor | None = None,
    avance: Callable[[float, float], None] | None = None,
) -> Resultado:
    """Ejecuta una misión completa y devuelve trayectorias y métricas.

    `avance` se llama de vez en cuando con (progreso 0-1, segundos simulados)
    para que una interfaz pueda mostrar una barra sin que el motor sepa de
    interfaces.
    """
    cfg.validar()
    sim, enj, ent = cfg.simulacion, cfg.enjambre, cfg.entorno
    motor = motor or seleccionar(sim.usar_gpu)
    xp = motor.xp

    altura = enj.altura_vuelo_m
    huella = enj.dron.huella_m(altura)

    campo = mod_entorno.construir(
        ent, cfg.comportamiento.obst_radio_influencia_m, motor=motor
    )
    viento = Viento(ent.viento, motor, sim.semilla)
    formacion = Formacion(enj.formacion, enj.n_drones, altura, motor)
    ruta = RutaBarrido(ent, formacion, huella, enj.v_crucero_ms)
    malla = MallaCobertura(ent, sim.celda_cobertura_m, huella / 2.0, motor)
    modelo = ModeloCinematico(enj.dron, motor)
    comp = Comportamientos(cfg.comportamiento, enj, motor)
    metricas = Metricas(cfg, motor)
    registro = RegistroTrayectorias(
        motor, [0.0, 0.0, 0.0], [ent.lado_x_m, ent.lado_y_m, ent.altura_max_m]
    )

    # El enjambre arranca ya formado sobre el inicio de la ruta.
    posicion = formacion.en_mundo(ruta.guia(), ruta.sentido)
    velocidad_aire = xp.zeros_like(posicion)

    n_pasos = int(sim.duracion_max_s / sim.dt_s)
    cada = sim.pasos_por_registro
    radio = enj.dron.radio_m
    v_max = enj.dron.v_max_horizontal_ms

    registro.anotar(0.0, posicion)
    reloj = time.perf_counter()
    paso = 0
    t = 0.0
    motivo = "duración máxima alcanzada"

    for paso in range(1, n_pasos + 1):
        t = paso * sim.dt_s

        viento.avanzar(sim.dt_s)
        aire = viento.en(posicion)
        velocidad_suelo = velocidad_aire + aire

        cercanos = campo.consultar(posicion)
        vecinos = comp.vecinos(posicion)
        puestos = formacion.en_mundo(ruta.guia(), ruta.sentido)
        error_puesto = xp.linalg.norm(puestos - posicion, axis=1)

        aceleracion = comp.total(
            comp.hacia_puesto(
                posicion, velocidad_suelo, puestos, v_max, ruta.velocidad_guia()
            ),
            comp.evitar_obstaculos(velocidad_suelo, cercanos),
            comp.anticolision(posicion, velocidad_suelo, vecinos),
            comp.separacion(vecinos),
            comp.cohesion(posicion, vecinos),
        )

        posicion, velocidad_aire = modelo.avanzar(
            posicion, velocidad_aire, aceleracion, aire, sim.dt_s
        )

        # Espacio aéreo permitido. Al topar, se anula la velocidad vertical:
        # de lo contrario seguiría integrándose contra el tope y el dron
        # saldría disparado al dejar de tocarlo.
        altura_nueva = xp.clip(posicion[:, 2], ent.altura_min_m, ent.altura_max_m)
        topa = altura_nueva != posicion[:, 2]
        posicion = xp.concatenate([posicion[:, :2], altura_nueva[:, None]], axis=1)
        velocidad_aire = xp.concatenate(
            [velocidad_aire[:, :2], xp.where(topa, 0.0, velocidad_aire[:, 2])[:, None]], axis=1
        )

        choque_entorno = (
            (cercanos.dentro | (cercanos.distancia < radio)).any(axis=1)
            if cercanos.hay_candidatos
            else xp.zeros(enj.n_drones, dtype=bool)
        )

        metricas.paso(
            vecinos.distancia_minima, choque_entorno, error_puesto,
            velocidad_aire, velocidad_suelo,
        )
        malla.marcar(posicion, paso)
        ruta.avanzar(sim.dt_s, float(motor.a_numpy(error_puesto).mean()))

        if paso % cada == 0:
            registro.anotar(t, posicion)
            metricas.muestrear(t, malla.porcentaje, error_puesto, velocidad_suelo, ruta.progreso)
            if avance is not None:
                avance(ruta.progreso, t)

        if ruta.completada:
            motivo = "ruta de barrido completada"
            break

    motor.sincronizar()
    segundos_reloj = time.perf_counter() - reloj

    if paso % cada != 0:
        registro.anotar(t, posicion)
        metricas.muestrear(
            t, malla.porcentaje, xp.linalg.norm(puestos - posicion, axis=1),
            velocidad_aire + viento.en(posicion), ruta.progreso,
        )

    resumen = metricas.resumen(malla.porcentaje, t, ent.superficie_m2)
    resumen["eficacia"]["motivo_fin"] = motivo
    resumen["eficacia"]["progreso_ruta_pct"] = round(ruta.progreso * 100.0, 1)

    return Resultado(
        config=cfg,
        resumen=resumen,
        serie=metricas.serie,
        registro=registro,
        cobertura=malla.a_numpy(),
        obstaculos=_muestra_obstaculos(campo, motor, sim.max_obstaculos_visor),
        info={
            "dispositivo": motor.nombre,
            "dispositivo_detalle": motor.descripcion,
            "gpu_solicitada": sim.usar_gpu,
            "segundos_de_reloj": round(segundos_reloj, 2),
            "pasos": paso,
            "ms_por_paso": round(segundos_reloj / max(paso, 1) * 1000.0, 3),
            "veces_tiempo_real": round(t / max(segundos_reloj, 1e-9), 2),
            "obstaculos_totales": len(campo),
            "frente_formacion_m": round(formacion.frente_m, 1),
            "ancho_pasada_m": round(ruta.ancho_pasada, 1),
            "pasadas": ruta.n_pasadas,
            "altura_vuelo_m": round(altura, 2),
            "huella_m": round(huella, 2),
            "tiempo_ideal_s": round(ruta.tiempo_estimado_s(), 1),
        },
    )


def _muestra_obstaculos(campo, motor: Motor, tope: int) -> dict:
    """Muestra de obstáculos para el visor.

    Un bosque de 10 km² tiene medio millón de troncos y el navegador no puede
    dibujarlos: se manda una muestra y el visor advierte de que lo es.
    """
    azar = np.random.default_rng(0)
    cilindros = motor.a_numpy(campo.cilindros)
    cajas = motor.a_numpy(campo.cajas)
    total = len(cilindros) + len(cajas)

    if total > tope and total:
        cuota_cil = int(round(tope * len(cilindros) / total))
        if len(cilindros) > cuota_cil:
            cilindros = cilindros[azar.choice(len(cilindros), cuota_cil, replace=False)]
        cuota_caj = tope - len(cilindros)
        if len(cajas) > cuota_caj:
            cajas = cajas[azar.choice(len(cajas), max(cuota_caj, 0), replace=False)]

    return {
        "cilindros": cilindros,
        "cajas": cajas,
        "total_real": total,
        "es_muestra": total > tope,
    }
