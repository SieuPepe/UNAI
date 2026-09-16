"""Banco de pruebas: dónde está el punto de cruce entre CPU y GPU.

El proyecto afirma que a 100 drones la GPU es más lenta que la CPU. Eso no se
supone: se mide, y en la máquina concreta de cada cual. Este módulo cronometra
el paso de simulación completo para varios tamaños de enjambre en los
dispositivos disponibles.

La razón de fondo es que cada operación sobre matrices cuesta del orden de 5-10
microsegundos en despacharse a la GPU, se opere sobre cien números o sobre diez
millones, y un paso encadena decenas de operaciones. Hasta que las matrices no
son lo bastante grandes, ese peaje domina.
"""

from __future__ import annotations

import time
from dataclasses import replace

import numpy as np

from .calculo import Motor, gpu_disponible, seleccionar
from .comportamientos import Comportamientos
from .config import Config, ConfigFormacion
from .entorno import construir
from .vuelo import ModeloCinematico


def medir(n_drones: int, motor: Motor, pasos: int = 200, entorno: str = "campo") -> float:
    """Milisegundos por paso, ya descontado el calentamiento."""
    cfg = Config()
    cfg = replace(
        cfg,
        enjambre=replace(
            cfg.enjambre, n_drones=n_drones,
            formacion=ConfigFormacion("linea", separacion_max_m=10.0),
        ),
        entorno=replace(cfg.entorno, tipo=entorno),
    )
    xp = motor.xp
    campo = construir(cfg.entorno, cfg.comportamiento.obst_radio_influencia_m, motor=motor)
    comp = Comportamientos(cfg.comportamiento, cfg.enjambre, motor)
    modelo = ModeloCinematico(cfg.enjambre.dron, motor)

    azar = np.random.default_rng(0)
    posicion = motor.array(
        np.column_stack([
            azar.uniform(0, 1000, n_drones),
            azar.uniform(0, 1000, n_drones),
            np.full(n_drones, 5.0),
        ])
    )
    velocidad = xp.zeros_like(posicion)
    viento = xp.zeros_like(posicion)
    puestos = posicion + 1.0

    def un_paso():
        cercanos = campo.consultar(posicion)
        vecinos = comp.vecinos(posicion)
        a = comp.total(
            comp.hacia_puesto(posicion, velocidad, puestos, 15.0),
            comp.evitar_obstaculos(velocidad, cercanos),
            comp.anticolision(posicion, velocidad, vecinos),
            comp.separacion(vecinos),
            comp.cohesion(posicion, vecinos),
        )
        return modelo.avanzar(posicion, velocidad, a, viento, 0.02)

    for _ in range(10):        # calentamiento: compilación diferida y cachés
        un_paso()
    motor.sincronizar()

    inicio = time.perf_counter()
    for _ in range(pasos):
        un_paso()
    motor.sincronizar()
    return (time.perf_counter() - inicio) / pasos * 1000.0


def ejecutar(tamanos: list[int], pasos: int = 200) -> list[dict]:
    hay_gpu, motivo = gpu_disponible()
    print(f"\n  CPU: {seleccionar(False).descripcion}")
    print(f"  GPU: {motivo}\n")

    motores = [seleccionar(False)]
    if hay_gpu:
        motores.append(seleccionar(True))

    cabecera = f"  {'drones':>8}" + "".join(f"{m.nombre.upper():>12}" for m in motores)
    if hay_gpu:
        cabecera += f"{'ventaja GPU':>14}"
    print(cabecera)
    print("  " + "-" * (len(cabecera) - 2))

    filas = []
    for n in tamanos:
        tiempos = {}
        for motor in motores:
            try:
                tiempos[motor.nombre] = medir(n, motor, pasos)
            except MemoryError:
                tiempos[motor.nombre] = float("nan")
        linea = f"  {n:>8}" + "".join(f"{tiempos[m.nombre]:>11.3f}m" for m in motores)
        if hay_gpu:
            razon = tiempos["cpu"] / max(tiempos["gpu"], 1e-9)
            linea += f"{razon:>13.2f}×"
        print(linea)
        filas.append({"drones": n, **tiempos})

    if hay_gpu:
        cruce = next((f["drones"] for f in filas if f["cpu"] > f["gpu"]), None)
        print(
            f"\n  Punto de cruce: {'a partir de ' + str(cruce) + ' drones' if cruce else 'no alcanzado en este rango: la CPU gana siempre'}"
        )
    else:
        print("\n  Sin GPU no hay comparación posible. Para instalarla: pip install cupy-cuda12x")
    print()
    return filas
