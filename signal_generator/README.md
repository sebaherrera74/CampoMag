# Generador de Señales (Raspberry Pi)

Aplicación GUI (Tkinter) para generar señales analógicas mediante:
- MCP4725 (DAC I2C, salida 0–3.3 V aprox.)
- PWM por GPIO + filtro RC (salida aproximada 0–3.3 V tras filtro)

## Requisitos

- Raspberry Pi OS con Python 3
- Para MCP4725:
  - Habilitar I2C: `sudo raspi-config` → Interface Options → I2C → Enable
  - Cableado: VCC→3V3, GND→GND, SDA→SDA, SCL→SCL
  - Dirección por defecto `0x60` (puede variar)
- Para PWM (GPIO):
  - Demonio pigpio activo
  - Filtro RC externo (p. ej., R=3.3 kΩ, C=10 nF) desde GPIO a GND

## Instalación

```bash
sudo apt update
sudo apt install -y python3-pip python3-tk python3-pigpio pigpio
pip3 install -r /workspace/signal_generator/requirements.txt
# Para PWM: activar el demonio
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

## Ejecución

```bash
python3 /workspace/signal_generator/signal_gui.py
```

## Uso en Google Colab (simulación)

1. Sube el archivo `SignalGenerator_Simulation.ipynb` a Colab o ábrelo desde Google Drive.
2. Ejecuta las celdas. Si deseas controles interactivos, instala widgets:

```bash
pip install ipywidgets matplotlib
```

3. Ajusta los sliders y visualiza la señal en voltios (asumiendo Vref 3.3 V).

## Uso

1. Elige "MCP4725 (I2C)" o "PWM (GPIO)".
2. Ajusta parámetros:
   - Forma de onda: Sine, Square, Triangle, Sawtooth, DC
   - Frecuencia (Hz), Amplitud (0..1 de escala completa), Offset (0..1)
   - fs (Hz): frecuencia de muestreo/actualización
   - MCP4725: dirección I2C (hex, p. ej. 0x60)
   - PWM: GPIO (por defecto 18) y frecuencia PWM (≥10 kHz recomendado)
3. Clic en "Iniciar" para generar, "Detener" para parar.

Notas:
- La amplitud se interpreta como fracción de escala completa. El offset también.
- Señales son unipolares (0..3.3 V aprox.) tras el DAC o el filtro.
- Para exactitud superior usa MCP4725; para soluciones rápidas usa PWM+RC.

## Seguridad

- No excedas 3.3 V en los pines GPIO.
- No conectes cargas de baja impedancia directamente.