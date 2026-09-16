"""Entornos y campo de obstáculos.

Los cuatro entornos comparten una única representación interna —una lista de
cilindros (troncos, farolas) y otra de cajas alineadas (edificios, paredes,
estanterías)— de modo que el mismo enjambre y la misma misión puedan lanzarse
en cualquiera de ellos y compararse (`docs/01`, §4).

Los obstáculos se indexan una sola vez en una rejilla uniforme cuyo lado es el
radio de influencia, de forma que preguntar "¿qué tengo cerca?" consulte nueve
celdas en vez de recorrer el medio millón de troncos de un bosque de 10 km².
La construcción del escenario ocurre siempre en la CPU (es una sola vez, y así
la semilla produce el mismo bosque en cualquier dispositivo); solo las tablas
resultantes viajan al dispositivo de cálculo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .calculo import Motor, seleccionar
from .config import ConfigEntorno

# Distancia devuelta para una plaza vacía de la rejilla: mayor que cualquier
# radio de influencia razonable, de modo que no influya en ninguna suma.
LEJOS = 1.0e9


@dataclass(frozen=True)
class Vecindad:
    """Obstáculos próximos a cada dron. Matrices de forma (n_drones, n_candidatos)."""

    distancia: object
    """Distancia a la SUPERFICIE del obstáculo, no a su centro."""

    direccion: object
    """Vector unitario del obstáculo hacia el dron: la dirección del empujón."""

    dentro: object
    """Cierto si el dron está dentro del volumen del obstáculo: ha colisionado."""

    @property
    def hay_candidatos(self) -> bool:
        return self.distancia.shape[1] > 0


class _RejillaPrimitivas:
    """Índice espacial de primitivas por su huella en planta.

    El número de plazas por celda se dimensiona con la celda más poblada, así
    que la consulta es exacta: no se descarta ningún obstáculo por rebosar.
    """

    def __init__(
        self,
        huellas: np.ndarray,
        lado_x: float,
        lado_y: float,
        celda: float,
        motor: Motor,
    ):
        self.motor = motor
        self.xp = motor.xp
        self.celda = float(celda)
        self.n_x = max(1, int(np.ceil(lado_x / self.celda)))
        self.n_y = max(1, int(np.ceil(lado_y / self.celda)))
        n_celdas = self.n_x * self.n_y

        if len(huellas) == 0:
            self.tabla = self.xp.asarray(np.full((n_celdas, 0), -1, dtype=np.int32))
            return

        i0 = np.clip((huellas[:, 0] / self.celda).astype(np.int64), 0, self.n_x - 1)
        j0 = np.clip((huellas[:, 1] / self.celda).astype(np.int64), 0, self.n_y - 1)
        i1 = np.clip((huellas[:, 2] / self.celda).astype(np.int64), 0, self.n_x - 1)
        j1 = np.clip((huellas[:, 3] / self.celda).astype(np.int64), 0, self.n_y - 1)

        # Inserción vectorizada: cada primitiva ocupa todas las celdas que toca
        # su huella. Un bucle por primitiva tardaba segundos con medio millón
        # de troncos.
        ancho = i1 - i0 + 1
        alto = j1 - j0 + 1
        total = ancho * alto
        base = np.cumsum(total) - total
        desplazamiento = np.arange(int(total.sum())) - np.repeat(base, total)
        ancho_rep = np.repeat(ancho, total)
        celdas = (
            (np.repeat(j0, total) + desplazamiento // ancho_rep) * self.n_x
            + (np.repeat(i0, total) + desplazamiento % ancho_rep)
        )
        indices = np.repeat(np.arange(len(huellas), dtype=np.int64), total)

        cuenta = np.bincount(celdas, minlength=n_celdas)
        tabla = np.full((n_celdas, int(cuenta.max())), -1, dtype=np.int32)

        # Posición de cada primitiva dentro de su celda, sin bucles por celda.
        orden = np.argsort(celdas, kind="stable")
        celdas_ord = celdas[orden]
        inicio = np.concatenate(([0], np.cumsum(cuenta)[:-1]))
        ranura = np.arange(celdas_ord.size) - inicio[celdas_ord]
        tabla[celdas_ord, ranura] = indices[orden]

        self.tabla = self.xp.asarray(tabla)

    @property
    def plazas(self) -> int:
        return self.tabla.shape[1]

    def candidatos(self, xy):
        """Índices de primitivas en las 9 celdas que rodean a cada punto.

        Devuelve (n_puntos, 9·plazas); las plazas vacías valen -1.
        """
        xp = self.xp
        n = xy.shape[0]
        if self.plazas == 0:
            return xp.full((n, 0), -1, dtype=xp.int32)

        i = xp.clip((xy[:, 0] / self.celda).astype(xp.int64), 0, self.n_x - 1)
        j = xp.clip((xy[:, 1] / self.celda).astype(xp.int64), 0, self.n_y - 1)
        salto = xp.asarray([-1, 0, 1], dtype=xp.int64)
        vi = xp.clip(i[:, None] + salto[None, :], 0, self.n_x - 1)
        vj = xp.clip(j[:, None] + salto[None, :], 0, self.n_y - 1)
        celdas = (vj[:, :, None] * self.n_x + vi[:, None, :]).reshape(n, 9)
        return self.tabla[celdas].reshape(n, -1)


class CampoObstaculos:
    """Los obstáculos de un entorno, listos para consultar en bloque."""

    def __init__(
        self,
        cilindros: np.ndarray,
        cajas: np.ndarray,
        lado_x: float,
        lado_y: float,
        radio_influencia: float,
        max_candidatos: int = 16,
        motor: Motor | None = None,
    ):
        self.motor = motor or seleccionar(False)
        xp = self.xp = self.motor.xp

        # cilindros: (M, 5) -> cx, cy, radio, z_inferior, z_superior
        # cajas:     (K, 6) -> x0, y0, z0, x1, y1, z1
        cil = np.asarray(cilindros, dtype=np.float64).reshape(-1, 5)
        caj = np.asarray(cajas, dtype=np.float64).reshape(-1, 6)
        self.n_cilindros, self.n_cajas = len(cil), len(caj)
        self.radio_influencia = float(radio_influencia)
        self.max_candidatos = int(max_candidatos)
        """Obstáculos más próximos que se tienen en cuenta por dron.

        En un bosque denso las nueve celdas vecinas devuelven cientos de
        troncos, y calcularle a cada uno la geometría exacta cuesta más que la
        simulación entera. El término 1/d² del campo potencial (`docs/02`, §6)
        hace despreciable todo lo que no sea lo más cercano.
        """

        huella_cil = np.empty((self.n_cilindros, 4))
        if self.n_cilindros:
            huella_cil[:, 0] = cil[:, 0] - cil[:, 2]
            huella_cil[:, 1] = cil[:, 1] - cil[:, 2]
            huella_cil[:, 2] = cil[:, 0] + cil[:, 2]
            huella_cil[:, 3] = cil[:, 1] + cil[:, 2]
        huella_caj = caj[:, [0, 1, 3, 4]] if self.n_cajas else np.empty((0, 4))

        self.cilindros = xp.asarray(cil)
        self.cajas = xp.asarray(caj)
        # Tablas reducidas en float32 para la fase barata de preselección.
        self._cil_xy = xp.asarray(cil[:, :3].astype(np.float32))
        self._caj_xy = xp.asarray(huella_caj.astype(np.float32))

        self._rej_cil = _RejillaPrimitivas(huella_cil, lado_x, lado_y, radio_influencia, self.motor)
        self._rej_caj = _RejillaPrimitivas(huella_caj, lado_x, lado_y, radio_influencia, self.motor)

    def __len__(self) -> int:
        return self.n_cilindros + self.n_cajas

    def consultar(self, posiciones) -> Vecindad:
        """Distancia, dirección de empuje y penetración de los obstáculos cercanos."""
        xp = self.xp
        n = posiciones.shape[0]
        trozos_d, trozos_u, trozos_in = [], [], []

        idx = self._rej_cil.candidatos(posiciones[:, :2])
        if idx.shape[1]:
            idx = self._preseleccionar(idx, self._rango_cilindros(posiciones, idx))
            d, u, dentro = self._distancia_cilindros(posiciones, idx)
            trozos_d.append(d); trozos_u.append(u); trozos_in.append(dentro)

        idx = self._rej_caj.candidatos(posiciones[:, :2])
        if idx.shape[1]:
            idx = self._preseleccionar(idx, self._rango_cajas(posiciones, idx))
            d, u, dentro = self._distancia_cajas(posiciones, idx)
            trozos_d.append(d); trozos_u.append(u); trozos_in.append(dentro)

        if not trozos_d:
            return Vecindad(
                xp.empty((n, 0)), xp.empty((n, 0, 3)), xp.zeros((n, 0), dtype=bool)
            )
        return Vecindad(
            xp.concatenate(trozos_d, axis=1),
            xp.concatenate(trozos_u, axis=1),
            xp.concatenate(trozos_in, axis=1),
        )

    def hay_colision(self, posiciones, radio_dron: float):
        """Cierto para los drones que tocan o penetran algún obstáculo."""
        vecindad = self.consultar(posiciones)
        if not vecindad.hay_candidatos:
            return self.xp.zeros(posiciones.shape[0], dtype=bool)
        return (vecindad.dentro | (vecindad.distancia < radio_dron)).any(axis=1)

    # -- preselección ------------------------------------------------------- #

    def _preseleccionar(self, idx, rango):
        """Se queda con los `max_candidatos` más cercanos en planta."""
        if idx.shape[1] <= self.max_candidatos:
            return idx
        recorte = self.xp.argpartition(rango, self.max_candidatos - 1, axis=1)
        return self.xp.take_along_axis(idx, recorte[:, : self.max_candidatos], axis=1)

    def _rango_cilindros(self, p, idx):
        """Distancia horizontal al tronco, en float32: solo sirve para ordenar."""
        xp = self.xp
        valido = idx >= 0
        cil = self._cil_xy[xp.where(valido, idx, 0)]
        dx = p[:, None, 0].astype(xp.float32) - cil[..., 0]
        dy = p[:, None, 1].astype(xp.float32) - cil[..., 1]
        d = xp.sqrt(dx * dx + dy * dy) - cil[..., 2]
        return xp.where(valido, d, xp.float32(LEJOS))

    def _rango_cajas(self, p, idx):
        """Distancia horizontal al rectángulo en planta, no a su centro.

        Una estantería de 40 m tiene el centro lejos y la superficie al lado.
        """
        xp = self.xp
        valido = idx >= 0
        rect = self._caj_xy[xp.where(valido, idx, 0)]
        px = p[:, None, 0].astype(xp.float32)
        py = p[:, None, 1].astype(xp.float32)
        dx = xp.maximum(xp.maximum(rect[..., 0] - px, 0.0), px - rect[..., 2])
        dy = xp.maximum(xp.maximum(rect[..., 1] - py, 0.0), py - rect[..., 3])
        return xp.where(valido, dx * dx + dy * dy, xp.float32(LEJOS))

    # -- geometría ---------------------------------------------------------- #

    def _distancia_cilindros(self, p, idx):
        xp = self.xp
        valido = idx >= 0
        cil = self.cilindros[xp.where(valido, idx, 0)]          # (n, c, 5)

        dxy = p[:, None, :2] - cil[..., :2]
        rho = xp.linalg.norm(dxy, axis=-1)
        # Un dron exactamente sobre el eje no tiene dirección radial definida;
        # se le da una arbitraria pero estable para no dividir por cero.
        radial = xp.where(
            rho[..., None] > 1e-9,
            dxy / xp.maximum(rho, 1e-9)[..., None],
            xp.asarray([1.0, 0.0]),
        )

        q_xy = cil[..., :2] + radial * cil[..., 2:3]
        q_z = xp.clip(p[:, None, 2], cil[..., 3], cil[..., 4])
        v = xp.stack(
            [p[:, None, 0] - q_xy[..., 0], p[:, None, 1] - q_xy[..., 1], p[:, None, 2] - q_z],
            axis=-1,
        )
        d = xp.linalg.norm(v, axis=-1)

        dentro = (
            (rho < cil[..., 2]) & (p[:, None, 2] > cil[..., 3]) & (p[:, None, 2] < cil[..., 4])
        )
        u = xp.where(
            (d[..., None] > 1e-9) & ~dentro[..., None],
            v / xp.maximum(d, 1e-9)[..., None],
            xp.concatenate([radial, xp.zeros_like(radial[..., :1])], axis=-1),
        )
        return xp.where(valido & ~dentro, d, xp.where(dentro, 0.0, LEJOS)), u, valido & dentro

    def _distancia_cajas(self, p, idx):
        xp = self.xp
        valido = idx >= 0
        caja = self.cajas[xp.where(valido, idx, 0)]             # (n, c, 6)
        minimo, maximo = caja[..., :3], caja[..., 3:]

        q = xp.clip(p[:, None, :], minimo, maximo)
        v = p[:, None, :] - q
        d = xp.linalg.norm(v, axis=-1)
        dentro = d < 1e-9

        # Dentro de la caja se empuja hacia la cara más próxima.
        hacia_min = p[:, None, :] - minimo
        hacia_max = maximo - p[:, None, :]
        eje = xp.argmin(xp.minimum(hacia_min, hacia_max), axis=-1)
        signo = xp.where(
            xp.take_along_axis(hacia_min, eje[..., None], -1)
            < xp.take_along_axis(hacia_max, eje[..., None], -1),
            -1.0,
            1.0,
        )
        salida = xp.zeros_like(v)
        xp.put_along_axis(salida, eje[..., None], signo, axis=-1)

        u = xp.where(dentro[..., None], salida, v / xp.maximum(d, 1e-9)[..., None])
        return xp.where(valido, d, LEJOS), u, valido & dentro


# --------------------------------------------------------------------------- #
# Generadores de entorno
# --------------------------------------------------------------------------- #

def construir(
    cfg: ConfigEntorno,
    radio_influencia: float,
    max_candidatos: int = 16,
    motor: Motor | None = None,
) -> CampoObstaculos:
    """Crea el campo de obstáculos del entorno descrito por `cfg`.

    Depende solo de `cfg` y de su semilla: "bosque denso semilla 42" es
    siempre exactamente el mismo bosque (`docs/01`, §4).
    """
    cfg.validar()
    azar = np.random.default_rng(cfg.semilla)
    generador = {
        "campo": _campo_abierto,
        "urbano": _urbano,
        "bosque": _bosque,
        "interior": _interior,
    }[cfg.tipo]
    cilindros, cajas = generador(cfg, azar)
    return CampoObstaculos(
        cilindros, cajas, cfg.lado_x_m, cfg.lado_y_m, radio_influencia, max_candidatos, motor
    )


def _campo_abierto(cfg: ConfigEntorno, azar: np.random.Generator):
    """Espacio libre: el caso base, sin obstáculos. El viento hace el trabajo."""
    return np.empty((0, 5)), np.empty((0, 6))


def _urbano(cfg: ConfigEntorno, azar: np.random.Generator):
    """Manzanas rectangulares separadas por calles, con alturas variadas."""
    paso = cfg.manzana_m + cfg.calle_m
    n_x = max(1, int(cfg.lado_x_m // paso))
    n_y = max(1, int(cfg.lado_y_m // paso))
    ix, iy = np.meshgrid(np.arange(n_x), np.arange(n_y), indexing="xy")
    x0 = ix.ravel() * paso + cfg.calle_m / 2.0
    y0 = iy.ravel() * paso + cfg.calle_m / 2.0
    alturas = azar.uniform(cfg.altura_edificio_min_m, cfg.altura_edificio_max_m, x0.size)
    cajas = np.stack(
        [x0, y0, np.zeros_like(x0), x0 + cfg.manzana_m, y0 + cfg.manzana_m, alturas], axis=1
    )
    return np.empty((0, 5)), cajas


def _bosque(cfg: ConfigEntorno, azar: np.random.Generator):
    """Troncos cilíndricos repartidos al azar, con densidad configurable.

    A 0,05 troncos/m² sobre 10 km² son 500.000 árboles: caben en memoria de
    sobra (`docs/04`, §9), y la rejilla los consulta sin recorrerlos.
    """
    n = int(round(cfg.densidad_arboles_m2 * cfg.superficie_m2))
    if n <= 0:
        return np.empty((0, 5)), np.empty((0, 6))
    x = azar.uniform(0.0, cfg.lado_x_m, n)
    y = azar.uniform(0.0, cfg.lado_y_m, n)
    radio = cfg.radio_tronco_m * azar.uniform(0.6, 1.6, n)
    alto = azar.uniform(cfg.altura_arbol_min_m, cfg.altura_arbol_max_m, n)
    return np.stack([x, y, radio, np.zeros(n), alto], axis=1), np.empty((0, 6))


def _interior(cfg: ConfigEntorno, azar: np.random.Generator):
    """Recinto cerrado con paredes perimetrales y filas de estanterías."""
    grosor = 0.4
    lx, ly, techo = cfg.lado_x_m, cfg.lado_y_m, cfg.altura_techo_m
    cajas = [
        [0.0, 0.0, 0.0, grosor, ly, techo],
        [lx - grosor, 0.0, 0.0, lx, ly, techo],
        [0.0, 0.0, 0.0, lx, grosor, techo],
        [0.0, ly - grosor, 0.0, lx, ly, techo],
    ]
    paso = cfg.estanteria_ancho_m + cfg.pasillo_m
    y = cfg.pasillo_m
    while y + cfg.estanteria_ancho_m < ly - cfg.pasillo_m:
        x = cfg.pasillo_m
        while x + cfg.estanteria_largo_m < lx - cfg.pasillo_m:
            cajas.append(
                [x, y, 0.0, x + cfg.estanteria_largo_m,
                 y + cfg.estanteria_ancho_m, cfg.estanteria_alto_m]
            )
            x += cfg.estanteria_largo_m + cfg.pasillo_m
        y += paso
    return np.empty((0, 5)), np.array(cajas, dtype=np.float64)
