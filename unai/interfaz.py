"""Ventana de lanzamiento.

Los tres controles obligatorios son el **número de drones**, la **distancia
máxima entre drones** y la **casilla de GPU** (`docs/01`, §5.1). El resto de
parámetros están por comodidad.

La ventana muestra en vivo las magnitudes derivadas —frente de barrido, altura
sin solape, pasadas, duración estimada— para ver el efecto de cada cambio antes
de lanzar. Ahí está el valor: la diferencia entre una formación en línea y una
en columna son minutos frente a horas.

Tkinter viene incluido con Python en Windows y macOS. En Linux se instala
aparte (`sudo apt install python3-tk`).
"""

from __future__ import annotations

import queue
import threading
import time
import traceback
import webbrowser
from dataclasses import replace
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox, ttk

from .config import Config, ConfigEntorno, ConfigFormacion
from .estimacion import resumen_previo

_DERIVADAS = [
    ("altura_vuelo_m", "Altura de vuelo", "m"),
    ("huella_m", "Huella de la cámara", "m"),
    ("redundancia", "Redundancia", "×"),
    ("frente_m", "Frente de barrido", "m"),
    ("ancho_pasada_m", "Ancho de pasada", "m"),
    ("pasadas", "Pasadas", ""),
    ("tiempo_ideal_texto", "Duración ideal", ""),
    ("visor_mb", "Tamaño del visor", "MB"),
    ("reloj_estimado_texto", "Cálculo estimado", ""),
    ("hilos", "Hilos que se usarán", ""),
]


class Ventana:
    def __init__(self, raiz: Tk):
        self.raiz = raiz
        raiz.title("UNAI — simulador de enjambres de drones")
        raiz.minsize(880, 620)

        self.cola: queue.Queue = queue.Queue()
        self.trabajando = False
        self.campos: dict[str, StringVar] = {}
        self.usar_gpu = BooleanVar(value=False)
        self.abrir_al_terminar = BooleanVar(value=True)
        self.etiquetas: dict[str, ttk.Label] = {}

        marco = ttk.Frame(raiz, padding=12)
        marco.grid(sticky="nsew")
        raiz.columnconfigure(0, weight=1)
        raiz.rowconfigure(0, weight=1)
        marco.columnconfigure(0, weight=0)
        marco.columnconfigure(1, weight=1)
        marco.rowconfigure(0, weight=1)

        self._construir_entradas(marco)
        self._construir_derivadas(marco)
        self._construir_pie(marco)
        self._recalcular()

    # -- construcción ------------------------------------------------------- #

    def _entrada(self, padre, fila, etiqueta, clave, valor, ancho=12):
        ttk.Label(padre, text=etiqueta).grid(row=fila, column=0, sticky="w", pady=2)
        var = StringVar(value=str(valor))
        var.trace_add("write", lambda *_: self._recalcular())
        ttk.Entry(padre, textvariable=var, width=ancho).grid(
            row=fila, column=1, sticky="ew", pady=2, padx=(8, 0)
        )
        self.campos[clave] = var
        return var

    def _combo(self, padre, fila, etiqueta, clave, valores, valor):
        ttk.Label(padre, text=etiqueta).grid(row=fila, column=0, sticky="w", pady=2)
        var = StringVar(value=valor)
        var.trace_add("write", lambda *_: self._recalcular())
        ttk.Combobox(
            padre, textvariable=var, values=list(valores), state="readonly", width=10
        ).grid(row=fila, column=1, sticky="ew", pady=2, padx=(8, 0))
        self.campos[clave] = var
        return var

    def _construir_entradas(self, padre):
        caja = ttk.LabelFrame(padre, text="Parámetros", padding=10)
        caja.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        caja.columnconfigure(1, weight=1)
        por_omision = Config()

        fila = 0
        ttk.Label(caja, text="ENJAMBRE", font=("", 8, "bold")).grid(
            row=fila, column=0, sticky="w", pady=(0, 2)
        )
        fila += 1
        self._entrada(caja, fila, "Número de drones", "drones", por_omision.enjambre.n_drones)
        fila += 1
        self._entrada(
            caja, fila, "Distancia máx. entre drones (m)", "separacion",
            por_omision.enjambre.formacion.separacion_max_m,
        )
        fila += 1
        self._combo(caja, fila, "Formación", "formacion", ConfigFormacion.FORMAS, "linea")
        fila += 1
        self._entrada(caja, fila, "Columnas (si rejilla)", "columnas", 10)
        fila += 1
        self._entrada(caja, fila, "Filas (si rejilla)", "filas", 10)
        fila += 1
        self._entrada(caja, fila, "Altura de vuelo (m, vacío = auto)", "altura", "")
        fila += 1
        self._entrada(caja, fila, "Velocidad de crucero (m/s)", "velocidad",
                      por_omision.enjambre.v_crucero_ms)
        fila += 1
        self._entrada(caja, fila, "Radio de comunicación (m)", "r_com",
                      por_omision.enjambre.r_com_m)

        fila += 1
        ttk.Separator(caja, orient="horizontal").grid(
            row=fila, column=0, columnspan=2, sticky="ew", pady=8
        )
        fila += 1
        ttk.Label(caja, text="ENTORNO", font=("", 8, "bold")).grid(row=fila, column=0, sticky="w")
        fila += 1
        self._combo(caja, fila, "Tipo", "entorno", ConfigEntorno.TIPOS, "campo")
        fila += 1
        self._entrada(caja, fila, "Superficie (km²)", "km2", 10.0)
        fila += 1
        self._entrada(caja, fila, "Viento medio (m/s)", "viento", 0.0)
        fila += 1
        self._entrada(caja, fila, "Árboles por m² (bosque)", "densidad", 0.05)

        fila += 1
        ttk.Separator(caja, orient="horizontal").grid(
            row=fila, column=0, columnspan=2, sticky="ew", pady=8
        )
        fila += 1
        ttk.Label(caja, text="SIMULACIÓN", font=("", 8, "bold")).grid(
            row=fila, column=0, sticky="w"
        )
        fila += 1
        self._entrada(caja, fila, "Duración máxima (s)", "duracion",
                      por_omision.simulacion.duracion_max_s)
        fila += 1
        self._entrada(caja, fila, "Semilla", "semilla", por_omision.simulacion.semilla)
        fila += 1
        ttk.Checkbutton(
            caja, text="Usar GPU", variable=self.usar_gpu, command=self._recalcular
        ).grid(row=fila, column=0, columnspan=2, sticky="w", pady=(6, 0))
        fila += 1
        ttk.Checkbutton(
            caja, text="Abrir el visor al terminar", variable=self.abrir_al_terminar
        ).grid(row=fila, column=0, columnspan=2, sticky="w")

    def _construir_derivadas(self, padre):
        caja = ttk.LabelFrame(padre, text="Lo que sale de estos parámetros", padding=10)
        caja.grid(row=0, column=1, sticky="nsew")
        caja.columnconfigure(1, weight=1)
        caja.rowconfigure(len(_DERIVADAS) + 1, weight=1)

        for i, (clave, etiqueta, unidad) in enumerate(_DERIVADAS):
            ttk.Label(caja, text=etiqueta).grid(row=i, column=0, sticky="w", pady=1)
            valor = ttk.Label(caja, text="—", font=("", 10, "bold"))
            valor.grid(row=i, column=1, sticky="e", pady=1)
            ttk.Label(caja, text=unidad, width=3).grid(row=i, column=2, sticky="w")
            self.etiquetas[clave] = valor

        ttk.Separator(caja, orient="horizontal").grid(
            row=len(_DERIVADAS), column=0, columnspan=3, sticky="ew", pady=8
        )
        self.avisos = ttk.Label(
            caja, text="", wraplength=380, justify="left", foreground="#a05000"
        )
        self.avisos.grid(row=len(_DERIVADAS) + 1, column=0, columnspan=3, sticky="nw")

    def _construir_pie(self, padre):
        pie = ttk.Frame(padre)
        pie.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        pie.columnconfigure(1, weight=1)

        self.boton = ttk.Button(pie, text="Simular", command=self._lanzar)
        self.boton.grid(row=0, column=0, padx=(0, 10))
        self.barra = ttk.Progressbar(pie, mode="determinate", maximum=100)
        self.barra.grid(row=0, column=1, sticky="ew")
        ttk.Button(pie, text="Guardar configuración", command=self._guardar).grid(
            row=0, column=2, padx=(10, 0)
        )
        self.estado = ttk.Label(pie, text="Listo.")
        self.estado.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))

    # -- lógica ------------------------------------------------------------- #

    def _numero(self, clave, tipo=float, por_omision=None):
        texto = self.campos[clave].get().strip().replace(",", ".")
        if not texto:
            return por_omision
        return tipo(texto)

    def construir_config(self) -> Config:
        """Traduce los campos de la ventana a una configuración validada.

        Es la misma que consume la línea de órdenes, de modo que cualquier
        lanzamiento manual se puede repetir después sin la ventana.
        """
        base = Config()
        forma = self.campos["formacion"].get()
        formacion = replace(
            base.enjambre.formacion,
            forma=forma,
            separacion_max_m=self._numero("separacion", float, 10.0),
            columnas=self._numero("columnas", int) if forma == "rejilla" else None,
            filas=self._numero("filas", int) if forma == "rejilla" else None,
            altura_m=self._numero("altura", float),
        )
        enjambre = replace(
            base.enjambre,
            n_drones=self._numero("drones", int, 100),
            v_crucero_ms=self._numero("velocidad", float, 15.0),
            r_com_m=self._numero("r_com", float, 150.0),
            formacion=formacion,
        )
        lado = (max(self._numero("km2", float, 10.0), 1e-6) * 1e6) ** 0.5
        viento = self._numero("viento", float, 0.0) or 0.0
        semilla = self._numero("semilla", int, 42)
        entorno = replace(
            base.entorno,
            tipo=self.campos["entorno"].get(),
            lado_x_m=lado,
            lado_y_m=lado,
            semilla=semilla,
            densidad_arboles_m2=self._numero("densidad", float, 0.05),
            viento=replace(
                base.entorno.viento,
                velocidad_media_ms=viento,
                turbulencia_sigma_ms=viento * 0.25,
            ),
        )
        simulacion = replace(
            base.simulacion,
            duracion_max_s=self._numero("duracion", float, 2400.0),
            semilla=semilla,
            usar_gpu=self.usar_gpu.get(),
        )
        nombre = f"{entorno.tipo}-{enjambre.n_drones}d-{formacion.forma}"
        return replace(
            base, nombre=nombre, enjambre=enjambre, entorno=entorno, simulacion=simulacion
        )

    def _recalcular(self, *_):
        try:
            datos = resumen_previo(self.construir_config())
        except Exception as exc:
            for etiqueta in self.etiquetas.values():
                etiqueta.config(text="—")
            self.avisos.config(text=f"Configuración no válida: {exc}", foreground="#b00020")
            return
        for clave, etiqueta in self.etiquetas.items():
            valor = datos[clave]
            etiqueta.config(text=f"{valor:g}" if isinstance(valor, float) else str(valor))
        self.avisos.config(
            text="\n\n".join(f"• {a}" for a in datos["avisos"]), foreground="#a05000"
        )

    def _guardar(self):
        try:
            cfg = self.construir_config().validar()
        except Exception as exc:
            messagebox.showerror("Configuración no válida", str(exc))
            return
        ruta = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialfile=f"{cfg.nombre}.json",
        )
        if ruta:
            cfg.guardar(ruta)
            self.estado.config(
                text=f"Configuración guardada en {ruta}. "
                     f"Se puede relanzar con: python -m unai simular --config {Path(ruta).name}"
            )

    def _lanzar(self):
        if self.trabajando:
            return
        try:
            cfg = self.construir_config().validar()
        except Exception as exc:
            messagebox.showerror("Configuración no válida", str(exc))
            return

        self.trabajando = True
        self.boton.config(state="disabled")
        self.barra["value"] = 0
        self.estado.config(text="Simulando...")
        threading.Thread(target=self._trabajo, args=(cfg,), daemon=True).start()
        self.raiz.after(100, self._vaciar_cola)

    def _trabajo(self, cfg: Config):
        """Hilo de cálculo. La ventana no se congela mientras simula."""
        try:
            from .simulacion import simular
            from .visor import generar

            resultado = simular(
                cfg, avance=lambda p, t: self.cola.put(("avance", (p, t)))
            )
            destino = Path("resultados") / f"{cfg.nombre}-{time.strftime('%Y%m%d-%H%M%S')}"
            destino.mkdir(parents=True, exist_ok=True)
            cfg.guardar(destino / "config.json")
            visor = generar(resultado, destino / "visor.html")
            self.cola.put(("fin", (resultado, visor)))
        except Exception:
            self.cola.put(("error", traceback.format_exc()))

    def _vaciar_cola(self):
        try:
            while True:
                tipo, carga = self.cola.get_nowait()
                if tipo == "avance":
                    progreso, t = carga
                    self.barra["value"] = progreso * 100
                    self.estado.config(text=f"Simulando... {progreso * 100:.1f} %  ·  t = {t:.0f} s")
                elif tipo == "fin":
                    self._terminar(*carga)
                    return
                elif tipo == "error":
                    self.trabajando = False
                    self.boton.config(state="normal")
                    self.estado.config(text="Error durante la simulación.")
                    messagebox.showerror("Error", carga)
                    return
        except queue.Empty:
            pass
        if self.trabajando:
            self.raiz.after(100, self._vaciar_cola)

    def _terminar(self, resultado, visor: Path):
        self.trabajando = False
        self.boton.config(state="normal")
        self.barra["value"] = 100
        r = resultado.resumen
        self.estado.config(
            text=(
                f"Cobertura {r['eficacia']['cobertura_final_pct']} % en "
                f"{r['eficacia']['tiempo_mision_s']:.0f} s  ·  "
                f"{r['seguridad']['colisiones_entre_drones']} colisiones entre drones, "
                f"{r['seguridad']['colisiones_con_entorno']} con el entorno  ·  "
                f"separación mínima {r['seguridad']['separacion_minima_m']} m  ·  "
                f"{resultado.info['segundos_de_reloj']} s en {resultado.info['dispositivo']}  ·  "
                f"visor: {visor}"
            )
        )
        if self.abrir_al_terminar.get():
            webbrowser.open(visor.resolve().as_uri())


def abrir() -> None:
    raiz = Tk()
    Ventana(raiz)
    raiz.mainloop()
