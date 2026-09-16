"""Generación del visor: un único fichero HTML que se abre con doble clic.

Sin servidor, sin instalación, sin internet y sin librerías externas: el 3D se
dibuja a mano sobre un lienzo 2D. Una dependencia de una red de distribución
rompería la promesa de que el resultado se puede guardar, mandar por correo y
abrir dentro de tres años.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np

from .simulacion import Resultado

_PLANTILLA = Path(__file__).with_name("plantilla_visor.html")
_LADO_MAX_COBERTURA = 160
_MUY_LEJANO = np.iinfo(np.int32).max


def _reducir_cobertura(malla: np.ndarray, lado_max: int) -> tuple[np.ndarray, int, int]:
    """Agrupa la malla de cobertura en bloques, quedándose con la visita más temprana.

    La malla de trabajo tiene millón y medio de celdas y el navegador no puede
    dibujar tantos cuadrados por fotograma. Se conserva el instante más
    temprano de cada bloque, que es lo que hace falta para ver cómo se va
    pintando el mapa.
    """
    n_y, n_x = malla.shape
    bloque_y = max(1, int(np.ceil(n_y / lado_max)))
    bloque_x = max(1, int(np.ceil(n_x / lado_max)))

    relleno_y = (-n_y) % bloque_y
    relleno_x = (-n_x) % bloque_x
    ampliada = np.pad(malla, ((0, relleno_y), (0, relleno_x)), constant_values=-1)

    positiva = np.where(ampliada < 0, _MUY_LEJANO, ampliada)
    alto, ancho = ampliada.shape
    reducida = positiva.reshape(
        alto // bloque_y, bloque_y, ancho // bloque_x, bloque_x
    ).min(axis=(1, 3))
    reducida = np.where(reducida == _MUY_LEJANO, -1, reducida)
    return reducida.astype(np.int32), bloque_x, bloque_y


def _b64(datos: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(datos).tobytes()).decode("ascii")


def construir_payload(resultado: Resultado) -> dict:
    cfg = resultado.config
    ent, enj, sim = cfg.entorno, cfg.enjambre, cfg.simulacion
    reg = resultado.registro.a_dict()

    reducida, bloque_x, bloque_y = _reducir_cobertura(resultado.cobertura, _LADO_MAX_COBERTURA)
    n_y_red, n_x_red = reducida.shape
    paso_max = int(reducida.max()) if reducida.size and reducida.max() > 0 else 1

    obst = resultado.obstaculos
    aviso = []
    if obst["es_muestra"]:
        aviso.append(
            f"Se dibuja una muestra de {len(obst['cilindros']) + len(obst['cajas']):,} "
            f"de los {obst['total_real']:,} obstáculos.".replace(",", ".")
        )
    aviso.append(
        f"Trayectorias registradas a {sim.registro_hz:g} Hz "
        f"(física a {1 / sim.dt_s:g} Hz); el visor interpola."
    )
    if resultado.resumen["coste"]["autonomia_excedida"]:
        aviso.append("<b style='color:#f85149'>Autonomía excedida: misión no realizable.</b>")

    seguridad = resultado.resumen["seguridad"]
    eficacia = resultado.resumen["eficacia"]
    subtitulo = (
        f"{enj.n_drones} drones · {enj.formacion.forma} · {ent.tipo} · "
        f"{ent.superficie_m2 / 1e6:g} km² · sep. {enj.formacion.separacion_max_m:g} m"
    )

    return {
        "escena": {
            "titulo": f"UNAI — {cfg.nombre}",
            "subtitulo": subtitulo,
            "aviso": "<br>".join(aviso),
            "lado_x": ent.lado_x_m,
            "lado_y": ent.lado_y_m,
            "dt_paso": sim.dt_s,
            "dt_marco": 1.0 / sim.registro_hz,
            "radio_dron": enj.dron.radio_m,
            "d_seguridad": cfg.comportamiento.anti_distancia_seguridad_m,
        },
        "trayectorias": {
            "n_marcos": reg["n_marcos"],
            "n_drones": reg["n_drones"],
            "instantes": reg["instantes"],
            "minimo": reg["minimo"],
            "escala": reg["escala"],
            "datos": _b64(reg["datos"]),
        },
        "cobertura": {
            "n_x": int(n_x_red),
            "n_y": int(n_y_red),
            "celda_x": ent.lado_x_m / max(n_x_red, 1),
            "celda_y": ent.lado_y_m / max(n_y_red, 1),
            "paso_max": paso_max,
            "datos": _b64(reducida),
        },
        "obstaculos": {
            "cilindros": np.asarray(obst["cilindros"]).round(2).tolist(),
            "cajas": np.asarray(obst["cajas"]).round(2).tolist(),
        },
        "serie": {
            "t": [round(v, 2) for v in resultado.serie.t],
            "cobertura": [round(v, 3) for v in resultado.serie.cobertura],
            "separacion_minima": [round(v, 3) for v in resultado.serie.separacion_minima],
            "error_formacion": [round(v, 3) for v in resultado.serie.error_formacion],
            "polarizacion": [round(v, 4) for v in resultado.serie.polarizacion],
            "energia_wh": [round(v, 2) for v in resultado.serie.energia_wh],
        },
        "resumen": {"seguridad": seguridad, "eficacia": eficacia},
    }


def generar(resultado: Resultado, ruta: str | Path) -> Path:
    """Escribe el visor autónomo y devuelve su ruta."""
    plantilla = _PLANTILLA.read_text(encoding="utf-8")
    payload = json.dumps(construir_payload(resultado), ensure_ascii=False, separators=(",", ":"))
    if "/*__DATOS__*/" not in plantilla:
        raise RuntimeError("la plantilla del visor no contiene el marcador de datos")

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(plantilla.replace("/*__DATOS__*/", payload), encoding="utf-8")
    return ruta
