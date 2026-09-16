"""Configuración del simulador.

Todo parámetro del que dependa un resultado vive aquí y se puede fijar desde un
fichero, sin tocar código (principio 5 de `docs/01`). Las dataclases son
inmutables para que una configuración no pueda cambiar a mitad de simulación:
un resultado siempre corresponde exactamente a la configuración con la que se
guardó.
"""

from __future__ import annotations

import dataclasses
import json
import math
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------- #
# Dron
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ConfigDron:
    """Límites físicos de un aparato. Valores típicos de un multirrotor de 1,5 kg."""

    masa_kg: float = 1.5
    radio_m: float = 0.35
    """Radio físico. Dos drones a menos de 2·radio han colisionado."""

    v_max_horizontal_ms: float = 15.0
    v_max_ascenso_ms: float = 5.0
    v_max_descenso_ms: float = 3.0
    a_max_ms2: float = 9.81
    """Aceleración máxima. Con relación empuje/peso 2:1 sale (2-1)·g ≈ 9,81."""

    giro_max_rad_s: float = 2.0
    tau_respuesta_s: float = 0.5
    """Tiempo de respuesta del lazo de velocidad (`docs/02`, §4)."""

    camara_fov_grados: float = 90.0
    bateria_wh: float = 60.0
    area_rotores_m2: float = 0.18
    area_frontal_m2: float = 0.03
    coef_arrastre: float = 0.6
    figura_merito: float = 0.7
    """Rendimiento real del rotor frente al ideal de la teoría del disco."""

    def huella_m(self, altura_m: float) -> float:
        """Diámetro de la huella de la cámara en el suelo, a una altura dada."""
        return 2.0 * altura_m * math.tan(math.radians(self.camara_fov_grados) / 2.0)

    def altura_sin_solape_m(self, separacion_m: float) -> float:
        """Altura a la que la huella mide exactamente `separacion_m`.

        Es el acople altura-separación de `docs/04`, §3: volar más alto
        multiplica la redundancia por el cuadrado del exceso.
        """
        return separacion_m / (2.0 * math.tan(math.radians(self.camara_fov_grados) / 2.0))


# --------------------------------------------------------------------------- #
# Formación y enjambre
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ConfigFormacion:
    """Geometría del enjambre.

    Es el parámetro de mayor impacto del proyecto: decide el frente de barrido
    y con él el tiempo de misión (`docs/04`, §4).
    """

    forma: str = "linea"
    """`linea` (todos en ala), `rejilla` (filas × columnas) o `cuna` (en V)."""

    columnas: int | None = None
    """Drones a lo ancho del frente. Si es None se deduce de la forma."""

    filas: int | None = None
    separacion_max_m: float = 10.0
    """`d_max`: separación objetivo entre drones contiguos. Restricción blanda."""

    altura_m: float | None = None
    """Altura de vuelo. Si es None se deriva de la separación (sin solape)."""

    solape_fraccion: float = 0.15
    """Solape de la huella de la cámara entre drones contiguos.

    La altura a la que la huella mide exactamente la separación deja las
    huellas **tangentes**: se tocan en un punto y no se solapan. Sobre el papel
    eso basta para cubrirlo todo; en la práctica no deja margen ninguno, y
    cualquier desvío de posición, deriva de viento o variación de altura abre
    franjas sin reconocer. Medido: con tangencia exacta y las trayectorias
    alineadas con la rejilla de medición, la cobertura cae al 72,5 %.

    El mismo 10-20 % que el barrido en franjas reserva entre pasadas (`docs/02`,
    §10) hace falta también entre drones. Con 0 se recupera la tangencia."""

    angulo_cuna_grados: float = 45.0

    FORMAS = ("linea", "rejilla", "cuna")

    def validar(self, n_drones: int) -> None:
        if self.forma not in self.FORMAS:
            raise ValueError(f"forma desconocida: {self.forma!r}; opciones: {self.FORMAS}")
        if self.separacion_max_m <= 0:
            raise ValueError("separacion_max_m debe ser positiva")
        if self.forma == "rejilla":
            if not self.columnas or not self.filas:
                raise ValueError("la forma 'rejilla' exige 'columnas' y 'filas'")
            if self.columnas * self.filas < n_drones:
                raise ValueError(
                    f"rejilla de {self.filas}x{self.columnas} no da cabida a {n_drones} drones"
                )


@dataclass(frozen=True)
class ConfigEnjambre:
    n_drones: int = 100
    v_crucero_ms: float = 15.0
    r_com_m: float = 150.0
    """Radio de comunicación y percepción. Limita a qué vecinos ve cada dron.

    No puede elegirse libremente: para que la anticolisión vea venir un cruce
    con el horizonte que tiene configurado, hace falta

        r_com >= velocidad_de_cierre_maxima x horizonte = 2 x v_max x horizonte

    Con 15 m/s y un horizonte de 4 s salen 120 m. Un radio menor no da un
    enjambre "mas local": da un horizonte mas corto del que se cree tener, y
    por tanto una anticolision que reacciona tarde sin avisar.

    Con formacion cohesionada determina ademas cuanto tarda una orden en
    recorrer el frente (`docs/04`, §7).
    """

    k_subenjambres: int = 1
    formacion: ConfigFormacion = field(default_factory=ConfigFormacion)
    dron: ConfigDron = field(default_factory=ConfigDron)

    def validar(self) -> None:
        if self.n_drones < 1:
            raise ValueError("n_drones debe ser al menos 1")
        if self.r_com_m <= 0:
            raise ValueError("r_com_m debe ser positivo")
        if self.k_subenjambres < 1 or self.k_subenjambres > self.n_drones:
            raise ValueError("k_subenjambres debe estar entre 1 y n_drones")
        self.formacion.validar(self.n_drones)

    @property
    def altura_vuelo_m(self) -> float:
        """Altura efectiva: la configurada, o la que no produce solape."""
        if self.formacion.altura_m is not None:
            return self.formacion.altura_m
        return self.dron.altura_sin_solape_m(self.formacion.separacion_max_m) * (
            1.0 + self.formacion.solape_fraccion
        )


# --------------------------------------------------------------------------- #
# Entorno
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ConfigViento:
    """Viento medio con perfil de altura más turbulencia con memoria (`docs/02`, §8)."""

    velocidad_media_ms: float = 0.0
    direccion_grados: float = 0.0
    """Dirección HACIA la que sopla. 0° = hacia el Este, 90° = hacia el Norte."""

    altura_referencia_m: float = 10.0
    exponente_alfa: float = 0.14
    """Exponente de la ley de potencia: 0,1 liso (mar), 0,4 rugoso (ciudad)."""

    turbulencia_sigma_ms: float = 0.0
    tiempo_correlacion_s: float = 5.0
    """Memoria de las ráfagas. Con 0 s el viento sería ruido blanco irreal."""


@dataclass(frozen=True)
class ConfigEntorno:
    tipo: str = "campo"
    lado_x_m: float = 3162.0
    lado_y_m: float = 3162.0
    altura_max_m: float = 120.0
    altura_min_m: float = 2.0
    semilla: int = 42
    viento: ConfigViento = field(default_factory=ConfigViento)

    # --- urbano ---
    manzana_m: float = 80.0
    calle_m: float = 20.0
    altura_edificio_min_m: float = 10.0
    altura_edificio_max_m: float = 45.0

    # --- bosque ---
    densidad_arboles_m2: float = 0.05
    """0,05/m² son 500 árboles por hectárea: bosque de densidad media."""

    radio_tronco_m: float = 0.25
    altura_arbol_min_m: float = 8.0
    altura_arbol_max_m: float = 20.0

    # --- interior ---
    altura_techo_m: float = 12.0
    estanteria_largo_m: float = 40.0
    estanteria_ancho_m: float = 3.0
    estanteria_alto_m: float = 8.0
    pasillo_m: float = 6.0

    TIPOS = ("campo", "urbano", "bosque", "interior")

    def validar(self) -> None:
        if self.tipo not in self.TIPOS:
            raise ValueError(f"entorno desconocido: {self.tipo!r}; opciones: {self.TIPOS}")
        if self.lado_x_m <= 0 or self.lado_y_m <= 0:
            raise ValueError("las dimensiones de la zona deben ser positivas")
        if self.altura_min_m >= self.altura_max_m:
            raise ValueError("altura_min_m debe ser menor que altura_max_m")

    @property
    def superficie_m2(self) -> float:
        return self.lado_x_m * self.lado_y_m


# --------------------------------------------------------------------------- #
# Comportamiento
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ConfigPesos:
    """Pesos con que se suman las aceleraciones (`docs/02`, §4).

    Son los mandos que definen el carácter del enjambre: subir `anticolision`
    da drones prudentes que cumplen mal la misión; subir `puesto` da drones
    eficientes que rozan el choque.
    """

    puesto: float = 1.0
    obstaculos: float = 2.5
    anticolision: float = 2.0
    separacion: float = 1.5
    cohesion: float = 0.6


@dataclass(frozen=True)
class ConfigComportamiento:
    pesos: ConfigPesos = field(default_factory=ConfigPesos)

    puesto_ganancia: float = 1.2
    """Cuánta velocidad se pide por metro de desvío respecto al puesto."""

    obst_radio_influencia_m: float = 20.0
    obst_k: float = 120.0
    obst_tangencial: float = 0.8
    """Componente de rodeo de la barrera cercana (`docs/02`, §6)."""

    obst_horizonte_s: float = 2.2
    """Segundos de antelación con que se empieza a esquivar un obstáculo.

    El campo potencial 1/d² por sí solo no sirve a 15 m/s: a 17 metros vale
    0,009 m/s², o sea nada, y a un metro es enorme. El dron llegaría encima del
    árbol antes de notarlo. El esquive se decide por **tiempo hasta el
    impacto**, igual que la anticolisión entre drones, y el campo potencial
    queda como barrera de última defensa."""

    obst_ganancia_lateral: float = 14.0
    obst_ganancia_frenado: float = 0.45

    obst_margen_m: float = 1.0
    """Holgura que se quiere conservar respecto a la superficie del obstáculo."""

    obst_freno_fraccion: float = 0.6
    """Parte de la aceleración máxima que se reserva para frenar.

    El resto queda para esquivar y para cumplir la misión. Reservar el 100 %
    daría un dron que solo sabe frenar."""

    obst_ganancia_freno: float = 25.0
    """Con cuánta contundencia se corrige ir más rápido de lo permitido.

    Sin este término, el dron gasta su presupuesto de aceleración en apartarse
    de lado y llega demasiado rápido demasiado cerca: a 1,9 m de una pared con
    6,7 m/s hacia ella harían falta 11,9 m/s² para parar y solo hay 9,81. En
    ese punto ya no hay maniobra posible, por buena que sea la lógica de
    esquive. La regla es la del conductor: la velocidad de acercamiento nunca
    debe superar la que permite la distancia de frenado que queda."""

    anti_horizonte_s: float = 4.0
    """Cuántos segundos hacia el futuro mira la anticolisión (`docs/02`, §7)."""

    anti_distancia_seguridad_m: float = 4.0
    anti_ganancia: float = 8.0
    anti_reciproco: bool = True
    """Cada dron asume la mitad del esfuerzo; evita el 'baile del pasillo'."""

    sep_distancia_m: float = 2.5
    sep_k: float = 12.0

    anti_margen_m: float = 0.8
    anti_freno_fraccion: float = 0.6
    anti_ganancia_freno: float = 25.0
    """Límite de velocidad de acercamiento entre drones por distancia de frenado.

    Mismo principio que `obst_ganancia_freno`, aplicado a los pares de drones.
    Hace falta por la misma razón: cuando la formación se rompe para esquivar
    un bosque, los drones se empujan unos contra otros, y la lógica predictiva
    por punto de máxima aproximación decide *hacia dónde* apartarse pero no
    impide llegar demasiado rápido demasiado cerca. Como ambos drones frenan a
    la vez, la deceleración disponible es el doble."""

    cohesion_holgura: float = 1.0
    """Margen sobre `d_max` antes de que tire la fuerza de cohesión."""

    ruta_a_curva_fraccion: float = 0.5
    """Parte de la aceleración máxima que el guía reserva para doblar la esquina.

    Con la ruta de barrido tomada en seco, el enjambre se pasa de largo en cada
    giro: el error de formación salta de 0,01 m en recta a 16 m en el vértice."""

    bloqueo_umbral_ms: float = 0.5
    bloqueo_segundos: float = 3.0
    """Un dron por debajo del umbral durante este tiempo se considera bloqueado."""


# --------------------------------------------------------------------------- #
# Simulación
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ConfigSimulacion:
    dt_s: float = 0.02
    """50 Hz. La distancia crítica es la separación entre drones, no el
    obstáculo: a 0,05 s dos drones de frente recortan el 15 % de su
    separación en un paso (`docs/04`, §8)."""

    duracion_max_s: float = 2400.0
    registro_hz: float = 5.0
    """Las trayectorias se guardan a 5 Hz y el visor interpola; las métricas
    se calculan a la frecuencia completa."""

    celda_cobertura_m: float = 2.5
    semilla: int = 42
    modo_estricto: bool = False
    usar_gpu: bool = False
    """La casilla de GPU. A 100 drones se espera que la GPU sea más LENTA que
    la CPU: cada operación cuesta más en despacharse al chip que en resolverse
    sobre matrices de 100 filas. Compensa a partir de varios miles de drones.
    Si se marca y no hay GPU, se avisa de forma visible y se sigue en CPU."""

    max_obstaculos_visor: int = 4000
    """Un bosque tiene medio millón de troncos y el visor no puede dibujarlos
    todos: se le manda una muestra, y el visor lo indica."""
    """Si es cierto, superar `d_max` cuenta como fallo y no solo como métrica."""

    def validar(self) -> None:
        if self.dt_s <= 0:
            raise ValueError("dt_s debe ser positivo")
        if self.registro_hz <= 0 or self.registro_hz > 1.0 / self.dt_s:
            raise ValueError("registro_hz debe ser positivo y no superar 1/dt_s")
        if self.celda_cobertura_m <= 0:
            raise ValueError("celda_cobertura_m debe ser positiva")

    @property
    def pasos_por_registro(self) -> int:
        return max(1, round(1.0 / (self.registro_hz * self.dt_s)))


# --------------------------------------------------------------------------- #
# Configuración completa
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Config:
    nombre: str = "referencia"
    enjambre: ConfigEnjambre = field(default_factory=ConfigEnjambre)
    entorno: ConfigEntorno = field(default_factory=ConfigEntorno)
    comportamiento: ConfigComportamiento = field(default_factory=ConfigComportamiento)
    simulacion: ConfigSimulacion = field(default_factory=ConfigSimulacion)

    def validar(self) -> Config:
        self.enjambre.validar()
        self.entorno.validar()
        self.simulacion.validar()
        cierre_max = 2.0 * self.enjambre.dron.v_max_horizontal_ms
        r_necesario = cierre_max * self.comportamiento.anti_horizonte_s
        if self.enjambre.r_com_m < r_necesario:
            horizonte_real = self.enjambre.r_com_m / max(cierre_max, 1e-9)
            warnings.warn(
                f"r_com_m={self.enjambre.r_com_m:.0f} m es menor que los "
                f"{r_necesario:.0f} m que exige un horizonte de anticolisión de "
                f"{self.comportamiento.anti_horizonte_s:.1f} s a "
                f"{cierre_max:.0f} m/s de velocidad de cierre. El horizonte "
                f"efectivo será de solo {horizonte_real:.1f} s.",
                RuntimeWarning,
                stacklevel=2,
            )

        altura = self.enjambre.altura_vuelo_m
        if not (self.entorno.altura_min_m <= altura <= self.entorno.altura_max_m):
            raise ValueError(
                f"la altura de vuelo ({altura:.1f} m) queda fuera del espacio aéreo "
                f"permitido [{self.entorno.altura_min_m}, {self.entorno.altura_max_m}] m"
            )
        return self

    # -- serialización ------------------------------------------------------ #

    def a_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def guardar(self, ruta: str | Path) -> None:
        """Guarda la configuración junto al resultado.

        Sin esto, un resultado de hace tres meses es inservible (`docs/03`, §5).
        """
        Path(ruta).write_text(
            json.dumps(self.a_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def desde_dict(cls, datos: dict[str, Any]) -> Config:
        return _construir(cls, datos)

    @classmethod
    def desde_fichero(cls, ruta: str | Path) -> Config:
        ruta = Path(ruta)
        texto = ruta.read_text(encoding="utf-8")
        if ruta.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError as exc:  # pragma: no cover - depende del entorno
                raise ImportError(
                    "leer YAML requiere PyYAML (pip install pyyaml); "
                    "los ficheros .json no necesitan nada"
                ) from exc
            datos = yaml.safe_load(texto)
        else:
            datos = json.loads(texto)
        datos = datos or {}
        # Las descripciones de los ficheros de `configs/` son para quien lee,
        # no parámetros: se retiran antes de construir.
        datos = {k: v for k, v in datos.items() if not k.startswith("_")}
        return cls.desde_dict(datos)


def _construir(cls: type, datos: dict[str, Any]) -> Any:
    """Construye una dataclase anidada desde un diccionario, avisando de claves ajenas.

    Una clave mal escrita en un fichero de configuración se ignoraría en
    silencio y daría un resultado distinto del esperado sin decir por qué; más
    vale que falle.
    """
    campos = {f.name: f for f in dataclasses.fields(cls)}
    sobrantes = set(datos) - set(campos)
    if sobrantes:
        raise ValueError(
            f"{cls.__name__}: claves desconocidas {sorted(sobrantes)}; "
            f"admitidas: {sorted(campos)}"
        )
    argumentos: dict[str, Any] = {}
    for nombre, valor in datos.items():
        tipo = campos[nombre].type
        if isinstance(valor, dict) and dataclasses.is_dataclass(_resolver(tipo)):
            argumentos[nombre] = _construir(_resolver(tipo), valor)
        else:
            argumentos[nombre] = valor
    return cls(**argumentos)


_TIPOS_ANIDADOS = {
    "ConfigDron": ConfigDron,
    "ConfigFormacion": ConfigFormacion,
    "ConfigEnjambre": ConfigEnjambre,
    "ConfigViento": ConfigViento,
    "ConfigEntorno": ConfigEntorno,
    "ConfigPesos": ConfigPesos,
    "ConfigComportamiento": ConfigComportamiento,
    "ConfigSimulacion": ConfigSimulacion,
}


def _resolver(tipo: Any) -> Any:
    """Resuelve la anotación de tipo, que con `from __future__` llega como texto."""
    if isinstance(tipo, str):
        return _TIPOS_ANIDADOS.get(tipo.strip(), object)
    return tipo
