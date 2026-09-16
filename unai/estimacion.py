"""Magnitudes derivadas de una configuración, antes de simular.

Es lo que la ventana de lanzamiento muestra en vivo mientras se teclean los
parámetros. El valor está en verlo **antes**: la diferencia entre una formación
en línea y una en columna son minutos frente a horas, y más vale saberlo que
descubrirlo tras esperar (`docs/01`, §5.1).

No simula nada: son cuentas de servilleta, las mismas del `docs/04`.
"""

from __future__ import annotations

import math

from .config import Config

# Ajuste a medidas reales de `python -m unai banco` en CPU:
#   25 drones 0,415 ms | 50: 1,088 | 100: 3,224 | 200: 15,73 | 400: 70,37
# El término fijo es el sobrecoste por operación, que domina con enjambres
# pequeños; el exponente algo mayor que 2 refleja que la matriz de pares deja
# de caber en caché. Cada máquina es distinta: `unai banco` la mide.
_MS_FIJO = 0.25
_MS_POR_CIEN = 3.0
_EXPONENTE = 2.2
_DRONES_REFERENCIA = 100


def resumen_previo(cfg: Config) -> dict:
    """Devuelve las magnitudes derivadas y los avisos de coherencia."""
    enj, ent, sim, comp = cfg.enjambre, cfg.entorno, cfg.simulacion, cfg.comportamiento
    dron, form = enj.dron, enj.formacion

    altura = enj.altura_vuelo_m
    huella = dron.huella_m(altura)
    separacion = form.separacion_max_m

    # Frente de la formación según su forma, sin construirla.
    n = enj.n_drones
    if form.forma == "linea":
        anchos = n
    elif form.forma == "rejilla":
        anchos = min(int(form.columnas or n), n)
    else:  # cuña
        anchos = 2 * ((n + 1) // 2) - (1 if n % 2 else 0)
    frente = max(0.0, (anchos - 1) * separacion)
    if form.forma == "cuna":
        frente = max(0.0, (n - 1) * separacion * math.cos(math.radians(form.angulo_cuna_grados)))

    ancho_pasada = frente + huella
    pasadas = max(1, math.ceil(ent.lado_y_m / ancho_pasada))
    longitud = pasadas * ent.lado_x_m + (pasadas - 1) * (ent.lado_y_m / pasadas)
    tiempo_ideal = longitud / max(enj.v_crucero_ms, 1e-9)

    redundancia = (huella / separacion) ** 2 if separacion > 0 else float("inf")
    duracion = min(sim.duracion_max_s, tiempo_ideal * 1.6)
    marcos = int(duracion * sim.registro_hz) + 1
    mb_visor = marcos * n * 3 * 2 / 1e6 * 1.34
    celdas = math.ceil(ent.lado_x_m / sim.celda_cobertura_m) * math.ceil(
        ent.lado_y_m / sim.celda_cobertura_m
    )
    ms_paso = _MS_FIJO + _MS_POR_CIEN * (n / _DRONES_REFERENCIA) ** _EXPONENTE
    reloj = duracion / sim.dt_s * ms_paso / 1000.0

    return {
        "altura_vuelo_m": round(altura, 2),
        "altura_sin_solape_m": round(dron.altura_sin_solape_m(separacion), 2),
        "huella_m": round(huella, 2),
        "redundancia": round(redundancia, 2),
        "frente_m": round(frente, 1),
        "ancho_pasada_m": round(ancho_pasada, 1),
        "pasadas": pasadas,
        "longitud_ruta_m": round(longitud, 0),
        "tiempo_ideal_s": round(tiempo_ideal, 0),
        "tiempo_ideal_texto": _duracion(tiempo_ideal),
        "celdas_cobertura": celdas,
        "marcos_registro": marcos,
        "visor_mb": round(mb_visor, 2),
        "reloj_estimado_s": round(reloj, 0),
        "reloj_estimado_texto": _duracion(reloj),
        "r_com_minimo_m": round(2.0 * dron.v_max_horizontal_ms * comp.anti_horizonte_s, 0),
        "avisos": _avisos(cfg, redundancia, altura),
    }


def _avisos(cfg: Config, redundancia: float, altura: float) -> list[str]:
    enj, ent, comp = cfg.enjambre, cfg.entorno, cfg.comportamiento
    dron, form = enj.dron, enj.formacion
    avisos: list[str] = []

    minimo = 2.0 * dron.v_max_horizontal_ms * comp.anti_horizonte_s
    if enj.r_com_m < minimo:
        efectivo = enj.r_com_m / max(2.0 * dron.v_max_horizontal_ms, 1e-9)
        avisos.append(
            f"El radio de comunicación ({enj.r_com_m:.0f} m) no llega a los {minimo:.0f} m "
            f"que exige el horizonte de anticolisión: el horizonte real será de "
            f"{efectivo:.1f} s en vez de {comp.anti_horizonte_s:.1f} s."
        )
    if redundancia > 4.0:
        avisos.append(
            f"A {altura:.0f} m de altura la huella mide {dron.huella_m(altura):.0f} m y los "
            f"drones van a {form.separacion_max_m:.0f} m: cada punto lo miran "
            f"{redundancia:.0f} drones a la vez. La altura sin solape sería "
            f"{dron.altura_sin_solape_m(form.separacion_max_m):.1f} m."
        )
    elif redundancia < 0.6:
        avisos.append(
            f"La separación ({form.separacion_max_m:.0f} m) supera a la huella "
            f"({dron.huella_m(altura):.0f} m): quedarán franjas sin reconocer entre drones."
        )
    if ent.tipo == "bosque":
        hueco = 1.0 / math.sqrt(max(ent.densidad_arboles_m2, 1e-9))
        if hueco < form.separacion_max_m:
            avisos.append(
                f"En este bosque hay un árbol cada {hueco:.1f} m y la formación va a "
                f"{form.separacion_max_m:.0f} m: no cabe entera, se romperá y se recompondrá."
            )
    if cfg.simulacion.usar_gpu and enj.n_drones < 1000:
        avisos.append(
            f"Con {enj.n_drones} drones se espera que la GPU sea MÁS LENTA que la CPU: "
            f"las matrices son demasiado pequeñas para amortizar el lanzamiento."
        )
    return avisos


def _duracion(segundos: float) -> str:
    if segundos < 90:
        return f"{segundos:.0f} s"
    if segundos < 5400:
        return f"{segundos / 60:.1f} min"
    return f"{segundos / 3600:.1f} h"
