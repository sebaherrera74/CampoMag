import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

try:
    import matplotlib.pyplot as plt  # type: ignore
    HAS_MPL = True
except Exception:
    HAS_MPL = False

try:
    from scipy.io import wavfile  # type: ignore
    HAS_SCIPY = True
except Exception:
    HAS_SCIPY = False


WAVEFORMS = ("sine", "square", "triangle", "sawtooth", "dc")


def waveform_value_minus1_to_plus1(kind: str, phase_0_to_1: float) -> float:
    k = kind.lower()
    p = phase_0_to_1 - math.floor(phase_0_to_1)
    if k == "sine":
        return math.sin(2.0 * math.pi * p)
    if k == "square":
        return 1.0 if p < 0.5 else -1.0
    if k == "triangle":
        return 4.0 * abs(p - 0.5) - 1.0
    if k == "sawtooth":
        return 2.0 * p - 1.0
    if k == "dc":
        return 0.0
    return math.sin(2.0 * math.pi * p)


def generate_signal(kind: str, freq_hz: float, fs_hz: float, amplitude: float, offset: float, duration_s: float,
                    vref_volts: float) -> tuple[np.ndarray, np.ndarray]:
    n = int(duration_s * fs_hz)
    t = np.arange(n, dtype=np.float64) / fs_hz
    phase = (t * freq_hz) % 1.0
    vec = np.vectorize(lambda ph: waveform_value_minus1_to_plus1(kind, ph))
    y_m1_p1 = vec(phase)
    half_amp = 0.5 * amplitude
    y_0_1 = np.clip(offset + half_amp * y_m1_p1, 0.0, 1.0)
    volts = y_0_1 * vref_volts
    return t, volts


def save_csv(path: Path, t: np.ndarray, v: np.ndarray) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "volts"])
        for ti, vi in zip(t, v):
            w.writerow([f"{ti:.9f}", f"{vi:.6f}"])


def save_png(path: Path, t: np.ndarray, v: np.ndarray, title: str) -> None:
    if not HAS_MPL:
        raise RuntimeError("matplotlib no disponible. Instala con: pip install matplotlib")
    plt.figure(figsize=(9, 3))
    plt.plot(t * 1000.0, v)
    plt.xlabel("Tiempo (ms)")
    plt.ylabel("Voltaje (V)")
    plt.title(title)
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def save_wav(path: Path, v: np.ndarray, vref_volts: float, fs_hz: float) -> None:
    if not HAS_SCIPY:
        raise RuntimeError("scipy no disponible. Instala con: pip install scipy")
    # Normaliza 0..Vref a -1..+1 para audio
    x = (v / vref_volts) * 2.0 - 1.0
    x = np.clip(x, -1.0, 1.0)
    data = (x * 32767.0).astype(np.int16)
    wavfile.write(str(path), int(fs_hz), data)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Simulación de generador de señales (sin hardware)")
    p.add_argument("--waveform", choices=WAVEFORMS, default="sine")
    p.add_argument("--freq", type=float, default=200.0, help="Frecuencia de la señal (Hz)")
    p.add_argument("--fs", type=float, default=8000.0, help="Frecuencia de muestreo (Hz)")
    p.add_argument("--amp", type=float, default=0.8, help="Amplitud (0..1, fracción de escala completa)")
    p.add_argument("--offset", type=float, default=0.5, help="Offset (0..1, fracción de escala completa)")
    p.add_argument("--dur", type=float, default=0.05, help="Duración (s)")
    p.add_argument("--vref", type=float, default=3.3, help="Voltaje de referencia (V)")
    p.add_argument("--out", type=Path, default=Path("signal.png"), help="Archivo de salida (png/csv/wav)")
    p.add_argument("--show", action="store_true", help="Mostrar gráfico en pantalla (requiere matplotlib)")
    args = p.parse_args(argv)

    if not (0.0 <= args.amp <= 1.0):
        print("--amp debe estar en [0..1]", file=sys.stderr)
        return 2
    if not (0.0 <= args.offset <= 1.0):
        print("--offset debe estar en [0..1]", file=sys.stderr)
        return 2
    if args.fs < 100.0:
        print("--fs demasiado bajo", file=sys.stderr)
        return 2
    if args.freq < 0.0:
        print("--freq debe ser >= 0", file=sys.stderr)
        return 2

    t, v = generate_signal(args.waveform, args.freq, args.fs, args.amp, args.offset, args.dur, args.vref)

    out: Path = args.out
    suffix = out.suffix.lower()
    title = f"{args.waveform} | f={args.freq} Hz, fs={args.fs} Hz, amp={args.amp}, offset={args.offset}"
    if suffix == ".png":
        save_png(out, t, v, title)
        print(f"PNG guardado en {out}")
    elif suffix == ".csv":
        save_csv(out, t, v)
        print(f"CSV guardado en {out}")
    elif suffix == ".wav":
        save_wav(out, v, args.vref, args.fs)
        print(f"WAV guardado en {out}")
    else:
        print("Extensión no soportada. Usa .png, .csv o .wav", file=sys.stderr)
        return 2

    if args.show:
        if not HAS_MPL:
            print("matplotlib no disponible para --show", file=sys.stderr)
            return 2
        import matplotlib.pyplot as plt  # noqa: WPS433
        plt.figure(figsize=(9, 3))
        plt.plot(t * 1000.0, v)
        plt.xlabel("Tiempo (ms)")
        plt.ylabel("Voltaje (V)")
        plt.title(title)
        plt.grid(True)
        plt.tight_layout()
        plt.show()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

