# DIY Stream Deck con ESP32-8048S043 — fork Linux

## Que es

Stream Deck casero con pantalla tactil 4.3", **3 paginas de 12 botones** (36 acciones totales) configurables desde una **app nativa Linux (GTK4)**. URLs, apps, atajos de teclado, texto. Iconos personalizados con favicon automatico.

**Diferencias con el repo upstream** (`sintex85/diy-streamdeck`): ese estaba pensado para Mac/Windows con Chrome + Web Serial; aqui todo el flujo va a USB con un teclado virtual (uinput) y una GUI Linux que vive en bandeja.

## Hardware

- **Placa**: ESP32-8048S043 (ESP32-S3, 800x480 RGB, touch GT911, CH340 USB)
- **Conexion**: USB para todo (alimentacion, configuracion, atajos de teclado, URLs/apps). BLE opcional como fallback.

## Como funciona

1. **USB**: conecta el deck al PC. La app `streamdeck` lo detecta automaticamente en `/dev/ttyUSB0`.
2. **Configura** desde la GUI: pulsa cualquier boton para editarlo. Hay **3 pestañas** para las 3 paginas.
3. **Cambia de pagina** en el deck con **swipe horizontal** o con las flechas ◀ ▶ del sidebar; tambien desde la app.
4. **Pulsa un boton** en el deck → la app hace `xdg-open` (URL/app), inyecta atajo via uinput (Teclado), o escribe el texto (Texto).

### Tipos de accion

| Tipo | Maneja | Necesita |
|------|--------|----------|
| URL | `xdg-open <url>` desde la GUI | GUI ejecutandose |
| App | `xdg-open <protocolo>` (`spotify:`, `discord:`...) | GUI + app instalada con su protocolo registrado |
| Teclado | uinput (teclado virtual del kernel) | GUI ejecutandose, usuario en grupo `input` |
| Texto | uinput | GUI ejecutandose |

## Setup en una maquina nueva

```bash
# Dependencias del sistema (Ubuntu 24.04)
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 \
                 python3-serial python3-pil python3-evdev xdg-utils

# Permisos (cierra sesion despues)
sudo usermod -aG dialout,input $USER

# Clonar e instalar
git clone https://github.com/gorkaFM/diy-streamdeck.git
cd diy-streamdeck
./linux/install.sh
```

Despues:
- `streamdeck` lanza la GUI.
- Arranca minimizado al iniciar sesion (configurado en `~/.config/autostart/`).
- `./linux/uninstall.sh` para revertir.

## Flashear el firmware

El firmware esta en `firmware/` precompilado. Para flashear con `esptool` (no el binario macOS antiguo):

```bash
pip install --user esptool

esptool --chip esp32s3 --port /dev/ttyUSB0 --baud 460800 \
  write-flash --flash-mode dio --flash-freq 80m --flash-size 16MB \
  0x0000  firmware/button_counter.ino.bootloader.bin \
  0x8000  firmware/button_counter.ino.partitions.bin \
  0xe000  firmware/boot_app0.bin \
  0x10000 firmware/button_counter.ino.bin
```

## Recompilar firmware

```bash
# Toolchain (~600 MB en total)
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=$HOME/.local/bin sh
arduino-cli config init --overwrite
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@2.0.17
arduino-cli lib install "LovyanGFX@1.2.19" "NimBLE-Arduino@2.4.0"
git clone https://github.com/wakwak-koba/ESP32-BLE-Keyboard.git ~/Arduino/libraries/ESP32-BLE-Keyboard

# Compilar
arduino-cli compile \
  --fqbn "esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,FlashMode=qio,PartitionScheme=default_8MB,UploadSpeed=460800" \
  --build-path /tmp/streamdeck-build button_counter/

# Copiar binarios al firmware/ (para flasheos posteriores sin recompilar)
cp /tmp/streamdeck-build/button_counter.ino*.bin firmware/
```

## Hardware (config tecnica)

- **Touch GT911**: I2C addr 0x5D, I2C_NUM_0, SDA=GPIO19, SCL=GPIO20, pin_int=-1
- **Display**: LovyanGFX, `LGFX_ESP32S3_RGB_ESP32-8048S043.h`
- **BLE**: NimBLE 2.4.0 + ESP32-BLE-Keyboard 0.4.0 (wakwak-koba fork)
- **PSRAM**: OPI (8MB), **Flash**: QIO (16MB)
- Nota: la USB-C del board va a CH340 → UART, no a USB nativo del ESP32-S3 (los pins USB nativos los usa el touch). Por eso el deck no puede ser un teclado HID via USB y se inyectan teclas desde el PC con uinput.

## Protocolo serial (115200 baud)

Cambio v2: todos los comandos llevan ahora un campo `page` (0..2). Sin compatibilidad con el formato single-page del upstream.

| Direccion | Comando | Descripcion |
|-----------|---------|-------------|
| ESP32 → PC | `BTN:<page>:<idx>:<type>:<action>` | Boton pulsado |
| ESP32 → PC | `CFG:<page>:<idx>:<label>:<r,g,b>:<has_icon>:<sz,brd,lbl>:<type>:<action>` | Una entrada de config (en respuesta a GETALL) |
| ESP32 → PC | `CURPAGE:<n>` | Pagina actual del deck |
| ESP32 → PC | `PAGE:<n>` | Notificacion de cambio de pagina (swipe / flechas) |
| PC → ESP32 | `SET:<page>:<idx>:<label>:<r,g,b>:<sz,brd,lbl>` | Config visual |
| PC → ESP32 | `ACT:<page>:<idx>:<type>:<action>` | Config accion |
| PC → ESP32 | `ICON:<page>:<idx>:<size>:<base64>` | Enviar icono RGB565 |
| PC → ESP32 | `NOICON:<page>:<idx>` | Quitar icono |
| PC → ESP32 | `PAGE:<n>` | Cambiar pagina activa |
| PC → ESP32 | `GETALL` | Pedir toda la config (devuelve 36 lineas CFG + END) |
| PC → ESP32 | `STATUS` | Estado BLE + pagina actual |

## Cambios respecto al upstream

### Firmware (`button_counter/button_counter.ino`)
- Soporte para 3 paginas × 12 botones (36 acciones).
- Swipe horizontal en la zona de botones para cambiar de pagina; wrap-around.
- Sidebar reorganizado: BT, ◀▶ con indicador "1/3", Config, Brillo+, Brillo-, Lock.
- Maquina de estados de touch (TP_IDLE/PRESS/SWIPE) → no hay flash de "pressed" durante un swipe.
- Protocolo serial v2 con campo `page` en todos los comandos.
- Reconoce `super`/`meta` ademas de `cmd`/`win`/`gui` como modificador.
- Pantalla de info actualizada (apunta al fork y describe el flujo Linux).

### App Linux (`linux/streamdeck.py`)
- GTK4 + libadwaita single-file (~900 lineas).
- Auto-detecta el puerto serie y reconecta con backoff.
- 3 pestañas para las paginas; cambio bidireccional con el deck.
- Diálogo de edicion redimensionable con presets categorizados (GNOME/Edicion/Navegador/Multimedia + apps).
- Subida de iconos (cualquier formato → cache PNG → RGB565 → ESP32) y boton "🌐 Favicon".
- Auto-favicon al guardar un boton URL sin icono.
- Teclado virtual via `python3-evdev` + `/dev/uinput` para atajos y texto en Wayland/X11.
- Modo `--daemon` (sin GUI) y `--minimized` (autostart en bandeja).

## Estructura

```
button_counter/         -> Codigo fuente Arduino (3 paginas, swipe)
firmware/               -> Binarios precompilados + esptool antiguo (no usar)
linux/                  -> App nativa Linux + scripts de install/uninstall
docs/index.html         -> Web vieja del upstream (DEPRECATED, protocolo viejo)
```
