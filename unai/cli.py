"""Línea de órdenes de UNAI.

Es la interfaz principal para el uso por lotes: comparar configuraciones exige
lanzar decenas de simulaciones sin abrir ninguna ventana (`docs/03`, §3.1). La
ventana gráfica (`python -m unai ventana`) escribe exactamente la misma
configuración, de modo que un lanzamiento manual se puede repetir después aquí.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
import warnings
import webbrowser
from dataclasses import replace
from pathlib import Path

from .config import Config, ConfigEntorno, ConfigFormacion, ConfigSimulacion
from .estimacion import resumen_previo


def _aplicar(cfg: Config, args: argparse.Namespace) -> Config:
    """Superpone las opciones de la línea de órdenes sobre la configuración."""
    enj, ent, sim, form = cfg.enjambre, cfg.entorno, cfg.simulacion, cfg.enjambre.formacion

    cambios_form: dict = {}
    if args.separacion is not None:
        cambios_form["separacion_max_m"] = args.separacion
    if args.formacion is not None:
        cambios_form["forma"] = args.formacion
    if args.columnas is not None:
        cambios_form["columnas"] = args.columnas
    if args.filas is not None:
        cambios_form["filas"] = args.filas
    if args.altura is not None:
        cambios_form["altura_m"] = args.altura
    if cambios_form:
        form = replace(form, **cambios_form)

    cambios_enj: dict = {"formacion": form}
    if args.drones is not None:
        cambios_enj["n_drones"] = args.drones
    if args.r_com is not None:
        cambios_enj["r_com_m"] = args.r_com
    if args.velocidad is not None:
        cambios_enj["v_crucero_ms"] = args.velocidad
    enj = replace(enj, **cambios_enj)

    cambios_ent: dict = {}
    if args.entorno is not None:
        cambios_ent["tipo"] = args.entorno
    if args.lado is not None:
        cambios_ent["lado_x_m"] = args.lado
        cambios_ent["lado_y_m"] = args.lado
    if args.km2 is not None:
        lado = (args.km2 * 1e6) ** 0.5
        cambios_ent["lado_x_m"] = lado
        cambios_ent["lado_y_m"] = lado
    if args.viento is not None:
        cambios_ent["viento"] = replace(
            ent.viento, velocidad_media_ms=args.viento,
            turbulencia_sigma_ms=args.viento * 0.25,
        )
    if args.semilla is not None:
        cambios_ent["semilla"] = args.semilla
    if cambios_ent:
        ent = replace(ent, **cambios_ent)

    cambios_sim: dict = {}
    if args.duracion is not None:
        cambios_sim["duracion_max_s"] = args.duracion
    if args.semilla is not None:
        cambios_sim["semilla"] = args.semilla
    if args.dt is not None:
        cambios_sim["dt_s"] = args.dt
    if args.gpu:
        cambios_sim["usar_gpu"] = True
    if cambios_sim:
        sim = replace(sim, **cambios_sim)

    nombre = args.nombre or cfg.nombre
    return replace(cfg, nombre=nombre, enjambre=enj, entorno=ent, simulacion=sim)


def _cargar(args: argparse.Namespace) -> Config:
    base = Config.desde_fichero(args.config) if args.config else Config()
    return _aplicar(base, args)


def _opciones_comunes(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="fichero JSON o YAML de configuración de partida")
    p.add_argument("--nombre", help="nombre del experimento")
    p.add_argument("--drones", type=int, help="número de drones")
    p.add_argument("--separacion", type=float, help="distancia máxima entre drones, en metros")
    p.add_argument("--altura", type=float, help="altura de vuelo (por omisión, la que no solapa)")
    p.add_argument("--formacion", choices=ConfigFormacion.FORMAS)
    p.add_argument("--columnas", type=int)
    p.add_argument("--filas", type=int)
    p.add_argument("--entorno", choices=ConfigEntorno.TIPOS)
    p.add_argument("--lado", type=float, help="lado de la zona, en metros")
    p.add_argument("--km2", type=float, help="superficie de la zona, en km²")
    p.add_argument("--viento", type=float, help="viento medio, en m/s")
    p.add_argument("--velocidad", type=float, help="velocidad de crucero, en m/s")
    p.add_argument("--r-com", dest="r_com", type=float, help="radio de comunicación, en metros")
    p.add_argument("--duracion", type=float, help="duración máxima simulada, en segundos")
    p.add_argument("--dt", type=float, help="paso de integración, en segundos")
    p.add_argument("--semilla", type=int)
    p.add_argument("--gpu", action="store_true", help="usar GPU si la hay (ver docs/01, §5.1)")


def _guardar(resultado, destino: Path) -> Path:
    from .visor import generar

    destino.mkdir(parents=True, exist_ok=True)
    resultado.config.guardar(destino / "config.json")
    (destino / "metricas.json").write_text(
        json.dumps(
            {"resumen": resultado.resumen, "info": resultado.info}, indent=2, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    serie = resultado.serie
    with (destino / "serie.csv").open("w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(
            ["t_s", "cobertura_pct", "separacion_minima_m", "error_formacion_m",
             "polarizacion", "energia_wh", "progreso", "bloqueados"]
        )
        escritor.writerows(
            zip(serie.t, serie.cobertura, serie.separacion_minima, serie.error_formacion,
                serie.polarizacion, serie.energia_wh, serie.progreso, serie.bloqueados)
        )
    return generar(resultado, destino / "visor.html")


def _imprimir(resultado) -> None:
    r, i = resultado.resumen, resultado.info
    print(f"\n  Dispositivo      {i['dispositivo']} ({i['dispositivo_detalle']})")
    print(f"  Cálculo          {i['segundos_de_reloj']} s de reloj, "
          f"{i['ms_por_paso']} ms/paso, ×{i['veces_tiempo_real']} el tiempo real")
    print(f"  Formación        frente {i['frente_formacion_m']} m, "
          f"{i['pasadas']} pasadas de {i['ancho_pasada_m']} m")
    print(f"  Vuelo            {i['altura_vuelo_m']} m de altura, huella {i['huella_m']} m")
    print(f"\n  Cobertura        {r['eficacia']['cobertura_final_pct']} %  "
          f"(ruta al {r['eficacia']['progreso_ruta_pct']} %, {r['eficacia']['motivo_fin']})")
    if r["eficacia"]["tiempo_hasta_90pct_s"]:
        print(f"  Hasta el 90 %    {r['eficacia']['tiempo_hasta_90pct_s']} s")
    print(f"  Duración         {r['eficacia']['tiempo_mision_s']} s "
          f"(ideal {i['tiempo_ideal_s']} s)")
    print(f"\n  Colisiones       {r['seguridad']['colisiones_entre_drones']} entre drones, "
          f"{r['seguridad']['colisiones_con_entorno']} con el entorno")
    print(f"  Separación       mínima {r['seguridad']['separacion_minima_m']} m, "
          f"margen p5 {r['seguridad']['margen_seguridad_p5_m']} m")
    print(f"  Tiempo en riesgo {r['seguridad']['tiempo_en_riesgo_s']} s")
    print(f"\n  Formación        error medio {r['formacion']['error_medio_al_puesto_m']} m, "
          f"fuera de tolerancia {r['formacion']['fraccion_tiempo_fuera_de_formacion'] * 100:.1f} %")
    print(f"  Bloqueo          {r['formacion']['tiempo_bloqueado_medio_s']} s de media por dron")
    print(f"\n  Energía          {r['coste']['energia_total_wh']} Wh, "
          f"{r['coste']['energia_por_m2_cubierto_wh']} Wh/m²")
    print(f"  Batería          queda {r['coste']['bateria_restante_minima_pct']} % en el peor dron"
          + ("  ¡AUTONOMÍA EXCEDIDA!" if r["coste"]["autonomia_excedida"] else ""))


# --------------------------------------------------------------------------- #
# Órdenes
# --------------------------------------------------------------------------- #

def orden_estimar(args: argparse.Namespace) -> int:
    cfg = _cargar(args)
    datos = resumen_previo(cfg)
    print(f"\n  {cfg.enjambre.n_drones} drones · formación {cfg.enjambre.formacion.forma} · "
          f"separación {cfg.enjambre.formacion.separacion_max_m:g} m · entorno {cfg.entorno.tipo} · "
          f"{cfg.entorno.superficie_m2 / 1e6:g} km²\n")
    for clave, etiqueta in [
        ("altura_vuelo_m", "Altura de vuelo (m)"), ("huella_m", "Huella de la cámara (m)"),
        ("redundancia", "Redundancia (veces)"), ("frente_m", "Frente de barrido (m)"),
        ("ancho_pasada_m", "Ancho de pasada (m)"), ("pasadas", "Pasadas"),
        ("tiempo_ideal_texto", "Duración ideal"), ("visor_mb", "Tamaño del visor (MB)"),
        ("reloj_estimado_texto", "Cálculo estimado"),
    ]:
        print(f"    {etiqueta:<26} {datos[clave]}")
    for aviso in datos["avisos"]:
        print(f"\n  AVISO: {aviso}")
    print()
    return 0


def orden_simular(args: argparse.Namespace) -> int:
    from .simulacion import simular

    cfg = _cargar(args)
    previo = resumen_previo(cfg)
    for aviso in previo["avisos"]:
        print(f"AVISO: {aviso}")
    print(f"\nSimulando «{cfg.nombre}»: {cfg.enjambre.n_drones} drones, "
          f"{cfg.entorno.tipo}, {cfg.entorno.superficie_m2 / 1e6:g} km². "
          f"Duración ideal {previo['tiempo_ideal_texto']}, "
          f"cálculo estimado {previo['reloj_estimado_texto']}.")

    ultimo = [-1.0]

    def avance(progreso: float, t: float) -> None:
        if progreso - ultimo[0] >= 0.02:
            ultimo[0] = progreso
            barra = "█" * int(progreso * 30)
            print(f"\r  [{barra:<30}] {progreso * 100:5.1f} %  t={t:7.1f} s", end="", flush=True)

    resultado = simular(cfg, avance=avance)
    print("\r" + " " * 70 + "\r", end="")
    _imprimir(resultado)

    destino = Path(args.salida) / f"{cfg.nombre}-{time.strftime('%Y%m%d-%H%M%S')}"
    visor = _guardar(resultado, destino)
    print(f"\n  Resultados en    {destino}")
    print(f"  Visor            {visor}  ({visor.stat().st_size / 1e6:.2f} MB)\n")
    if args.abrir:
        webbrowser.open(visor.resolve().as_uri())
    return 0


def orden_lote(args: argparse.Namespace) -> int:
    """Repite una configuración con varias semillas y resume la dispersión.

    Comparar dos configuraciones ejecutando una vez cada una no demuestra nada:
    la diferencia puede ser enteramente suerte. Se reportan mediana y rango
    intercuartílico (`docs/03`, §3.1).
    """
    from .simulacion import simular

    cfg = _cargar(args)
    filas = []
    for k in range(args.semillas):
        semilla = (args.semilla or 0) + k
        actual = replace(
            cfg,
            entorno=replace(cfg.entorno, semilla=semilla),
            simulacion=replace(cfg.simulacion, semilla=semilla),
        )
        print(f"  semilla {semilla} ({k + 1}/{args.semillas})...", end=" ", flush=True)
        r = simular(actual)
        filas.append({
            "semilla": semilla,
            "cobertura_pct": r.resumen["eficacia"]["cobertura_final_pct"],
            "tiempo_s": r.resumen["eficacia"]["tiempo_mision_s"],
            "colisiones_drones": r.resumen["seguridad"]["colisiones_entre_drones"],
            "colisiones_entorno": r.resumen["seguridad"]["colisiones_con_entorno"],
            "separacion_minima_m": r.resumen["seguridad"]["separacion_minima_m"],
            "margen_p5_m": r.resumen["seguridad"]["margen_seguridad_p5_m"],
            "energia_wh": r.resumen["coste"]["energia_total_wh"],
            "error_formacion_m": r.resumen["formacion"]["error_medio_al_puesto_m"],
            "bloqueado_s": r.resumen["formacion"]["tiempo_bloqueado_medio_s"],
        })
        print(f"cobertura {filas[-1]['cobertura_pct']:.1f} %")

    destino = Path(args.salida) / f"lote-{cfg.nombre}-{time.strftime('%Y%m%d-%H%M%S')}"
    destino.mkdir(parents=True, exist_ok=True)
    cfg.guardar(destino / "config.json")
    with (destino / "lote.csv").open("w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=list(filas[0]))
        escritor.writeheader()
        escritor.writerows(filas)

    print(f"\n  {'métrica':<22}{'mediana':>10}{'Q1':>10}{'Q3':>10}")
    for clave in list(filas[0])[1:]:
        valores = sorted(v for v in (f[clave] for f in filas) if v is not None)
        if not valores:
            continue
        q1, q3 = _cuartiles(valores)
        print(f"  {clave:<22}{statistics.median(valores):>10.3f}{q1:>10.3f}{q3:>10.3f}")
    print(f"\n  Tabla en {destino / 'lote.csv'}\n")
    return 0


def _cuartiles(valores: list[float]) -> tuple[float, float]:
    n = len(valores)
    if n < 4:
        return valores[0], valores[-1]
    return statistics.median(valores[: n // 2]), statistics.median(valores[(n + 1) // 2:])


def orden_banco(args: argparse.Namespace) -> int:
    from .banco import ejecutar

    ejecutar([int(v) for v in args.drones_lista.split(",")], args.pasos)
    return 0


def orden_ventana(args: argparse.Namespace) -> int:
    try:
        from .interfaz import abrir
    except ImportError as exc:
        print(
            f"No se puede abrir la ventana: {exc}\n"
            "Tkinter viene incluido con Python en Windows y macOS. En Linux se "
            "instala aparte (por ejemplo: sudo apt install python3-tk).\n"
            "Mientras tanto se puede usar la línea de órdenes: python -m unai simular --help",
            file=sys.stderr,
        )
        return 1
    abrir()
    return 0


def principal(argv: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(
        prog="unai", description="UNAI — simulador de vuelo de enjambres de drones"
    )
    ordenes = analizador.add_subparsers(dest="orden", required=True)

    p = ordenes.add_parser("simular", help="lanza una simulación y genera el visor")
    _opciones_comunes(p)
    p.add_argument("--salida", default="resultados")
    p.add_argument("--abrir", action="store_true", help="abrir el visor al terminar")
    p.set_defaults(funcion=orden_simular)

    p = ordenes.add_parser("estimar", help="muestra las magnitudes derivadas sin simular")
    _opciones_comunes(p)
    p.set_defaults(funcion=orden_estimar)

    p = ordenes.add_parser("lote", help="repite con varias semillas y resume la dispersión")
    _opciones_comunes(p)
    p.add_argument("--semillas", type=int, default=20)
    p.add_argument("--salida", default="resultados")
    p.set_defaults(funcion=orden_lote)

    p = ordenes.add_parser("banco", help="mide CPU frente a GPU y busca el punto de cruce")
    p.add_argument("--drones-lista", default="50,100,500,2000")
    p.add_argument("--pasos", type=int, default=200)
    p.set_defaults(funcion=orden_banco)

    p = ordenes.add_parser("ventana", help="abre la ventana de lanzamiento")
    p.set_defaults(funcion=orden_ventana)

    args = analizador.parse_args(argv)
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        return args.funcion(args)
