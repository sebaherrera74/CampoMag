import threading
import time
import math
import sys
import traceback

import tkinter as tk
from tkinter import ttk, messagebox


class BackendError(Exception):
    pass


def clamp(value: float, min_value: float, max_value: float) -> float:
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def waveform_value_minus1_to_plus1(kind: str, phase_0_to_1: float) -> float:
    """Return waveform value in range [-1.0, 1.0] given phase in [0.0, 1.0)."""
    k = kind.lower()
    p = phase_0_to_1 - math.floor(phase_0_to_1)
    if k == "sine":
        return math.sin(2.0 * math.pi * p)
    if k == "square":
        return 1.0 if p < 0.5 else -1.0
    if k == "triangle":
        # Triangle centered at 0: rises to +1 at p=0.25, down to -1 at p=0.75
        return 4.0 * abs(p - 0.5) - 1.0
    if k == "sawtooth":
        return 2.0 * p - 1.0
    if k == "dc":
        return 0.0
    # Default fallback
    return math.sin(2.0 * math.pi * p)


class BaseBackend:
    def start(self, params: dict) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError


class MCP4725Backend(BaseBackend):
    def __init__(self) -> None:
        self._running = False
        self._thread = None
        self._dac = None

    def _connect(self, i2c_addr: int):
        try:
            import board  # type: ignore
            import busio  # type: ignore
            from adafruit_mcp4725 import MCP4725  # type: ignore
        except Exception as exc:
            raise BackendError(
                "Dependencias para MCP4725 no disponibles. Instala adafruit-blinka y adafruit-circuitpython-mcp4725"
            ) from exc

        i2c = busio.I2C(board.SCL, board.SDA)
        self._dac = MCP4725(i2c, address=i2c_addr)

    def start(self, params: dict) -> None:
        if self._running:
            return

        i2c_addr = params.get("i2c_addr", 0x60)
        fs_hz = float(params.get("fs_hz", 8000.0))
        freq_hz = float(params.get("freq_hz", 200.0))
        amplitude = float(params.get("amplitude", 0.8))  # 0..1 (full-scale fraction)
        offset = float(params.get("offset", 0.5))        # 0..1 (full-scale fraction)
        waveform = str(params.get("waveform", "Sine"))

        if not (0.0 <= amplitude <= 1.0):
            raise BackendError("Amplitud debe estar entre 0.0 y 1.0")
        if not (0.0 <= offset <= 1.0):
            raise BackendError("Offset debe estar entre 0.0 y 1.0")
        if fs_hz < 100.0:
            raise BackendError("Frecuencia de muestreo (fs) demasiado baja")

        self._connect(int(i2c_addr))

        self._running = True

        def _worker():
            try:
                vref_counts = 4095.0  # 12-bit DAC MCP4725
                # Convert amplitude given as fraction of full-scale (0..1) to half-amplitude for [-1..1] waveform
                half_amp = 0.5 * amplitude
                t_next = time.perf_counter()
                phase = 0.0
                phase_inc = freq_hz / fs_hz
                while self._running:
                    val_m1_p1 = waveform_value_minus1_to_plus1(waveform, phase)
                    val_0_1 = clamp(offset + half_amp * val_m1_p1, 0.0, 1.0)
                    raw = int(round(val_0_1 * vref_counts))
                    try:
                        self._dac.raw_value = raw  # type: ignore[attr-defined]
                    except Exception:
                        # Swallow transient I2C timing errors softly, but do not crash the worker
                        pass

                    phase += phase_inc
                    if phase >= 1.0:
                        phase -= 1.0

                    t_next += 1.0 / fs_hz
                    delay = t_next - time.perf_counter()
                    if delay > 0.0:
                        time.sleep(delay)
            except Exception:
                traceback.print_exc()
            finally:
                try:
                    # Set output to 0V on stop
                    if self._dac is not None:
                        self._dac.raw_value = 0  # type: ignore[attr-defined]
                except Exception:
                    pass

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None


class PWMRCBackend(BaseBackend):
    def __init__(self) -> None:
        self._running = False
        self._thread = None
        self._pi = None

    def _connect(self):
        try:
            import pigpio  # type: ignore
        except Exception as exc:
            raise BackendError(
                "Dependencia pigpio no disponible. Instala python3-pigpio y asegura pigpiod en ejecuci\u00f3n"
            ) from exc
        pigpio_mod = sys.modules["pigpio"]  # type: ignore[index]
        self._pi = pigpio_mod.pi()  # type: ignore[attr-defined]
        if not self._pi.connected:  # type: ignore[attr-defined]
            raise BackendError("No se pudo conectar a pigpio (\u00bfdaemon activo?).")

    def start(self, params: dict) -> None:
        if self._running:
            return

        gpio_pin = int(params.get("gpio_pin", 18))
        pwm_hz = int(params.get("pwm_hz", 20000))
        fs_hz = float(params.get("fs_hz", 4000.0))
        freq_hz = float(params.get("freq_hz", 100.0))
        amplitude = float(params.get("amplitude", 0.8))  # full-scale fraction
        offset = float(params.get("offset", 0.5))        # full-scale fraction
        waveform = str(params.get("waveform", "Sine"))

        if not (0 <= gpio_pin <= 27):
            raise BackendError("GPIO no v\u00e1lido")
        if pwm_hz < 1000:
            raise BackendError("Frecuencia PWM demasiado baja (recomendado \u2265 10 kHz)")
        if fs_hz < 100.0:
            raise BackendError("Frecuencia de actualizaci\u00f3n (fs) demasiado baja")

        self._connect()

        # Configure PWM
        try:
            self._pi.set_PWM_frequency(gpio_pin, pwm_hz)  # type: ignore[attr-defined]
            self._pi.set_PWM_range(gpio_pin, 255)         # type: ignore[attr-defined]
        except Exception as exc:
            raise BackendError("No se pudo configurar PWM en pigpio") from exc

        self._running = True

        def _worker():
            try:
                half_amp = 0.5 * amplitude
                t_next = time.perf_counter()
                phase = 0.0
                phase_inc = freq_hz / fs_hz
                while self._running:
                    val_m1_p1 = waveform_value_minus1_to_plus1(waveform, phase)
                    val_0_1 = clamp(offset + half_amp * val_m1_p1, 0.0, 1.0)
                    duty = int(round(val_0_1 * 255.0))
                    try:
                        self._pi.set_PWM_dutycycle(gpio_pin, duty)  # type: ignore[attr-defined]
                    except Exception:
                        pass

                    phase += phase_inc
                    if phase >= 1.0:
                        phase -= 1.0

                    t_next += 1.0 / fs_hz
                    delay = t_next - time.perf_counter()
                    if delay > 0.0:
                        time.sleep(delay)
            except Exception:
                traceback.print_exc()
            finally:
                try:
                    if self._pi is not None:
                        self._pi.set_PWM_dutycycle(gpio_pin, 0)  # type: ignore[attr-defined]
                except Exception:
                    pass

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Generador de Se\u00f1ales - Raspberry Pi")
        self.geometry("640x420")

        self._backend: BaseBackend | None = None
        self._running = False

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        pad = 8

        # Backend selection
        backend_frame = ttk.LabelFrame(self, text="Salida")
        backend_frame.pack(fill=tk.X, padx=pad, pady=(pad, 0))

        self.backend_var = tk.StringVar(value="MCP4725 (I2C)")
        ttk.Label(backend_frame, text="M\u00e9todo:").pack(side=tk.LEFT, padx=(pad, 4), pady=pad)
        self.backend_combo = ttk.Combobox(
            backend_frame,
            textvariable=self.backend_var,
            values=["MCP4725 (I2C)", "PWM (GPIO)"],
            state="readonly",
            width=20,
        )
        self.backend_combo.pack(side=tk.LEFT, padx=(0, pad), pady=pad)
        self.backend_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_backend_options())

        # Dynamic backend options
        self.backend_opts_frame = ttk.Frame(self)
        self.backend_opts_frame.pack(fill=tk.X, padx=pad, pady=(4, 0))

        # Waveform & signal params
        wf_frame = ttk.LabelFrame(self, text="Se\u00f1al")
        wf_frame.pack(fill=tk.X, padx=pad, pady=(pad, 0))

        self.waveform_var = tk.StringVar(value="Sine")
        ttk.Label(wf_frame, text="Forma:").grid(row=0, column=0, sticky=tk.W, padx=pad, pady=pad)
        self.waveform_combo = ttk.Combobox(
            wf_frame,
            textvariable=self.waveform_var,
            values=["Sine", "Square", "Triangle", "Sawtooth", "DC"],
            state="readonly",
            width=12,
        )
        self.waveform_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, pad), pady=pad)

        self.freq_var = tk.StringVar(value="200.0")
        ttk.Label(wf_frame, text="Frecuencia (Hz):").grid(row=0, column=2, sticky=tk.W, padx=pad, pady=pad)
        ttk.Entry(wf_frame, textvariable=self.freq_var, width=12).grid(row=0, column=3, sticky=tk.W, padx=(0, pad), pady=pad)

        self.amp_var = tk.StringVar(value="0.8")
        ttk.Label(wf_frame, text="Amplitud (0..1):").grid(row=1, column=0, sticky=tk.W, padx=pad, pady=pad)
        ttk.Entry(wf_frame, textvariable=self.amp_var, width=12).grid(row=1, column=1, sticky=tk.W, padx=(0, pad), pady=pad)

        self.offset_var = tk.StringVar(value="0.5")
        ttk.Label(wf_frame, text="Offset (0..1):").grid(row=1, column=2, sticky=tk.W, padx=pad, pady=pad)
        ttk.Entry(wf_frame, textvariable=self.offset_var, width=12).grid(row=1, column=3, sticky=tk.W, padx=(0, pad), pady=pad)

        # Control buttons
        ctrl_frame = ttk.Frame(self)
        ctrl_frame.pack(fill=tk.X, padx=pad, pady=pad)

        self.start_btn = ttk.Button(ctrl_frame, text="Iniciar", command=self._on_start)
        self.start_btn.pack(side=tk.LEFT, padx=(pad, 4))
        self.stop_btn = ttk.Button(ctrl_frame, text="Detener", command=self._on_stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, pad))

        self.status_var = tk.StringVar(value="Listo")
        ttk.Label(self, textvariable=self.status_var).pack(fill=tk.X, padx=pad, pady=(0, pad))

        self._refresh_backend_options()

    def _clear_backend_opts(self):
        for child in self.backend_opts_frame.winfo_children():
            child.destroy()

    def _refresh_backend_options(self):
        self._clear_backend_opts()
        pad = 8
        choice = self.backend_var.get()
        if choice.startswith("MCP4725"):
            frame = ttk.LabelFrame(self.backend_opts_frame, text="Opciones MCP4725")
            frame.pack(fill=tk.X, padx=pad, pady=(4, 0))

            self.i2c_addr_var = tk.StringVar(value="0x60")
            ttk.Label(frame, text="I2C addr:").grid(row=0, column=0, sticky=tk.W, padx=pad, pady=pad)
            ttk.Entry(frame, textvariable=self.i2c_addr_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=(0, pad), pady=pad)

            self.fs_var = tk.StringVar(value="8000")
            ttk.Label(frame, text="fs (Hz):").grid(row=0, column=2, sticky=tk.W, padx=pad, pady=pad)
            ttk.Entry(frame, textvariable=self.fs_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=(0, pad), pady=pad)
        else:
            frame = ttk.LabelFrame(self.backend_opts_frame, text="Opciones PWM (GPIO)")
            frame.pack(fill=tk.X, padx=pad, pady=(4, 0))

            self.gpio_pin_var = tk.StringVar(value="18")
            ttk.Label(frame, text="GPIO pin:").grid(row=0, column=0, sticky=tk.W, padx=pad, pady=pad)
            ttk.Entry(frame, textvariable=self.gpio_pin_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=(0, pad), pady=pad)

            self.pwm_hz_var = tk.StringVar(value="20000")
            ttk.Label(frame, text="PWM (Hz):").grid(row=0, column=2, sticky=tk.W, padx=pad, pady=pad)
            ttk.Entry(frame, textvariable=self.pwm_hz_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=(0, pad), pady=pad)

            self.fs_var = tk.StringVar(value="4000")
            ttk.Label(frame, text="fs (Hz):").grid(row=0, column=4, sticky=tk.W, padx=pad, pady=pad)
            ttk.Entry(frame, textvariable=self.fs_var, width=10).grid(row=0, column=5, sticky=tk.W, padx=(0, pad), pady=pad)

    def _get_common_params(self) -> dict:
        try:
            freq_hz = float(self.freq_var.get())
            amp = float(self.amp_var.get())
            offs = float(self.offset_var.get())
        except ValueError:
            raise BackendError("Valores de frecuencia/amplitud/offset no v\u00e1lidos")
        if freq_hz < 0.0:
            raise BackendError("La frecuencia debe ser \u2265 0")
        return {
            "waveform": self.waveform_var.get(),
            "freq_hz": freq_hz,
            "amplitude": amp,
            "offset": offs,
        }

    def _on_start(self):
        if self._running:
            return
        try:
            params = self._get_common_params()
            fs_hz = float(self.fs_var.get())
            params["fs_hz"] = fs_hz
            if self.backend_var.get().startswith("MCP4725"):
                # Parse hex I2C address like 0x60
                addr_txt = self.i2c_addr_var.get().strip().lower()
                i2c_addr = int(addr_txt, 16) if addr_txt.startswith("0x") else int(addr_txt)
                params["i2c_addr"] = i2c_addr
                self._backend = MCP4725Backend()
            else:
                gpio_pin = int(self.gpio_pin_var.get())
                pwm_hz = int(self.pwm_hz_var.get())
                params["gpio_pin"] = gpio_pin
                params["pwm_hz"] = pwm_hz
                self._backend = PWMRCBackend()

            assert self._backend is not None
            self._backend.start(params)
            self._running = True
            self._set_controls_enabled(False)
            self.status_var.set("Generando se\u00f1al...")
        except Exception as exc:
            self._backend = None
            messagebox.showerror("Error", str(exc))

    def _on_stop(self):
        if not self._running:
            return
        try:
            if self._backend is not None:
                self._backend.stop()
        finally:
            self._backend = None
            self._running = False
            self._set_controls_enabled(True)
            self.status_var.set("Detenido")

    def _set_controls_enabled(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.backend_combo.configure(state="readonly" if enabled else tk.DISABLED)
        for child in self.backend_opts_frame.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass
            for gc in getattr(child, 'winfo_children', lambda: [])():
                try:
                    gc.configure(state=state)
                except tk.TclError:
                    pass
        widgets = [self.waveform_combo]
        for w in widgets:
            try:
                w.configure(state="readonly" if enabled else tk.DISABLED)
            except tk.TclError:
                pass
        # Entries
        for entry in self._find_all_entries(self):
            try:
                entry.configure(state=state)
            except tk.TclError:
                pass
        # Start/Stop
        self.start_btn.configure(state=state)
        self.stop_btn.configure(state=(tk.DISABLED if enabled else tk.NORMAL))

    def _find_all_entries(self, parent):
        items = []
        for child in parent.winfo_children():
            if isinstance(child, ttk.Entry) or isinstance(child, tk.Entry):
                items.append(child)
            items.extend(self._find_all_entries(child))
        return items

    def _on_close(self):
        try:
            if self._backend is not None:
                self._backend.stop()
        except Exception:
            pass
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

