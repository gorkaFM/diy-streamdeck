# DIY Stream Deck — Linux edition

Stream Deck casero con pantalla táctil de 4.3" basado en ESP32-8048S043, con **3 páginas de 12 botones** (36 acciones) configurables desde una **app nativa Linux GTK4**. Atajos de teclado, URLs, apps y texto se inyectan vía USB — no hace falta Bluetooth.

> Fork de [`sintex85/diy-streamdeck`](https://github.com/sintex85/diy-streamdeck) reescrito para Linux. El upstream original usa Chrome + Web Serial + GitHub Pages; aquí se sustituye por una app nativa, se añaden páginas múltiples y se inyectan teclas a través de `/dev/uinput`.

---

## Tabla de contenidos
- [Hardware necesario](#hardware-necesario)
- [Características](#características)
- [Instalación rápida](#instalación-rápida)
- [Uso](#uso)
- [Cómo funciona](#cómo-funciona)
- [Flashear el firmware](#flashear-el-firmware)
- [Recompilar el firmware](#recompilar-el-firmware)
- [Configuración persistente](#configuración-persistente)
- [Resolución de problemas](#resolución-de-problemas)
- [Diferencias con el upstream](#diferencias-con-el-upstream)
- [Estructura del repo](#estructura-del-repo)
- [Créditos y licencia](#créditos-y-licencia)

---

## Hardware necesario

- Placa **ESP32-8048S043** (también llamada Sunton ESP32-S3 4.3"):
  - ESP32-S3, 16 MB Flash, 8 MB PSRAM (OPI)
  - Pantalla RGB 800×480
  - Touch capacitivo GT911 (I2C en GPIO19/20)
  - USB-C → CH340 → UART (no es USB nativo del S3)
- **Cable USB-C** (datos, no solo carga)
- **Linux** (probado en Ubuntu 24.04 LTS, GNOME 46, Wayland)

> ⚠ La USB-C del board va al chip CH340, no al USB nativo del ESP32-S3. Por eso el deck **no puede ser un teclado HID nativo USB** — los atajos se inyectan desde el PC vía `uinput`.

## Características

- **3 páginas × 12 botones** (36 acciones totales) con cambio por **swipe** horizontal o flechas ◀ ▶ del sidebar.
- **Pestañas con nombre personalizable** (Trabajo, Casa, Juegos…) persistidas en disco.
- **5 tipos de acción**:
  | Tipo | Maneja | Necesita |
  |------|--------|----------|
  | URL | `xdg-open <url>` | App ejecutándose |
  | App | `xdg-open <protocolo>` (`spotify:`, `discord:`…) | App + protocolo registrado |
  | Teclado | uinput | grupo `input` |
  | Texto | uinput | grupo `input` |
  | Ninguna | — | — |
- **Presets categorizados** en el editor: GNOME / Edición / Navegador / Multimedia + atajos comunes.
- **Iconos personalizados**: subes cualquier imagen → caché PNG → conversión a RGB565 → enviada al deck.
- **Auto-favicon** al guardar un botón URL sin icono (vía Google s2/favicons).
- **Botón "🌐 Favicon"** explícito en el editor para re-bajarlo cuando quieras.
- **Indicador de página** en el deck (3 puntitos + "1/3") y en la app (pestañas).
- **Reconexión automática** si desconectas y vuelves a conectar el USB.
- **Modo `--minimized`** para autostart sin ventana.
- **Modo `--daemon`** sin GUI (solo escucha el deck y abre URLs/apps).

## Instalación rápida

### 1. Dependencias del sistema (Ubuntu 24.04)

```bash
sudo apt install \
    python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 \
    python3-serial python3-pil python3-evdev xdg-utils
```

### 2. Permisos

```bash
sudo usermod -aG dialout,input $USER
# Cierra sesión y vuelve a entrar para aplicar los grupos
```

- `dialout`: acceso a `/dev/ttyUSB0` (puerto serie del deck)
- `input`: acceso a `/dev/uinput` (teclado virtual)

### 3. Clonar e instalar la app

```bash
git clone https://github.com/gorkaFM/diy-streamdeck.git
cd diy-streamdeck
./linux/install.sh
```

Esto instala:
- `~/.local/bin/streamdeck` (lanzador)
- `~/.local/share/diy-streamdeck/` (código + icono)
- `~/.local/share/applications/com.bitsytornillos.streamdeck.desktop` (en menú GNOME)
- `~/.local/share/icons/hicolor/scalable/apps/com.bitsytornillos.streamdeck.svg`
- `~/.config/autostart/com.bitsytornillos.streamdeck.desktop` (arranca con la sesión)

### 4. Flashear el firmware

Si ya tienes el deck con el firmware antiguo (single-page) o vienes de cero:

```bash
pip install --user esptool
./firmware/flashear_linux.sh /dev/ttyUSB0
```

(Detalles en [Flashear el firmware](#flashear-el-firmware).)

### 5. Lanzar

```bash
streamdeck
```

O búscalo como **Stream Deck** en el menú de aplicaciones de GNOME.

## Uso

### Configurar un botón

1. **Pulsa cualquier botón** de la rejilla en la app.
2. Se abre el diálogo (redimensionable). Por defecto verás:
   - **Aspecto**: etiqueta + color
   - **Acción**: tipo + valor + ayuda contextual + presets si aplica
   - **Icono**: subir imagen, descargar favicon, quitar
3. Lo secundario (mostrar texto / tamaño icono / marco) está en la fila **"Avanzado"** plegable al final.
4. Pulsa **Guardar**. La config se manda al deck por serial; la pantalla se actualiza al instante.

### Cambiar de página

- En el deck:
  - **Swipe horizontal** sobre la zona de botones (de izquierda a derecha = anterior, de derecha a izquierda = siguiente, con wrap-around).
  - **Flechas ◀ ▶** del sidebar (toca la mitad izquierda o derecha del item de página).
- En la app: pulsa la pestaña deseada del switcher.
- Los dos lados están sincronizados.

### Renombrar páginas

Menú **☰ → Renombrar páginas…**

Aparece un diálogo con 3 entradas, una por página. Pon el nombre que quieras (máx. 32 caracteres) y guarda. Las pestañas se actualizan en caliente.

### Atajos disponibles (tipo Teclado)

Al elegir tipo "Teclado", el editor muestra presets agrupados:

**GNOME / Ubuntu**
| Preset | Combo |
|--------|-------|
| Terminal | `ctrl+alt+t` |
| Cambiar ventana | `alt+tab` |
| Cerrar ventana | `alt+f4` |
| Bloquear pantalla | `super+l` |
| Maximizar / Restaurar | `super+up` / `super+down` |
| Tile izq / der | `super+left` / `super+right` |
| Pantalla completa | `f11` |
| Workspace ↓ / ↑ | `ctrl+alt+down` / `ctrl+alt+up` |
| Vista de Apps | `super+a` |
| Captura pantalla | `printscreen` |

**Edición**: `ctrl+c`, `ctrl+v`, `ctrl+x`, `ctrl+z`, `ctrl+shift+z`, `ctrl+a`, `ctrl+s`, `ctrl+f`, `ctrl+p`

**Navegador**: `ctrl+t`, `ctrl+w`, `ctrl+shift+t`, `ctrl+r`, `alt+left`, `alt+right`, `ctrl+shift+i`

**Multimedia**: `vol_up`, `vol_down`, `vol_mute`, `play_pause`, `next_track`, `prev_track`

Combos custom: cualquier combinación con modificadores `ctrl|shift|alt|super` + tecla simple (a-z, 0-9, F1-F12, enter, esc, tab, space, backspace, delete, up/down/left/right, home, end, pageup, pagedown, insert).

## Cómo funciona

```
   ┌─────────────────────┐  USB  ┌──────────────────────┐
   │  ESP32-8048S043     │◄─────►│   streamdeck (PC)    │
   │                     │ 115200│  GTK4 + libadwaita   │
   │  - Pantalla LCD     │  baud │  - 3 pestañas        │
   │  - Touch GT911      │       │  - Editor + presets  │
   │  - 36 botones (NVS) │       │  - Iconos / favicon  │
   │  - BLE Keyboard ┐   │       │  - uinput keyboard   │
   └─────────────────┼───┘       └─────────┬────────────┘
                     │ (opcional)          │
                     ▼                     ▼
              [Bluetooth host]   /dev/uinput → escritorio
```

- **Comunicación**: serial USB a 115 200 baud. Protocolo de líneas (ver `CLAUDE.md`).
- **Persistencia**:
  - Config de los 36 botones: NVS del ESP32 (se guarda al editar).
  - Iconos: PSRAM del ESP32 (volátil). La app los re-envía desde el caché local en cada reconexión.
  - Caché local: `~/.config/diy-streamdeck/icons/p<page>_b<idx>.png`.
  - Nombres de páginas: `~/.config/diy-streamdeck/settings.json`.
- **Acciones URL/App**: el firmware notifica `BTN:page:idx:type:action` por serial; la app llama a `xdg-open`.
- **Acciones Teclado/Texto**: la app las inyecta vía `evdev.UInput` (un teclado virtual del kernel). Funciona idéntico en X11 y Wayland.
- **BLE keyboard**: el firmware mantiene un servidor BLE HID (`StreamDeck`). Si lo emparejas, los atajos también van por aire — útil si quieres usar el deck con el PC apagado y un móvil/tablet.

## Flashear el firmware

```bash
pip install --user esptool   # solo la primera vez
./firmware/flashear_linux.sh /dev/ttyUSB0
```

Si tu deck no aparece en `/dev/ttyUSB0`:

```bash
ls /dev/ttyUSB* /dev/ttyACM*
```

Pásale el correcto:

```bash
./firmware/flashear_linux.sh /dev/ttyACM0
```

Si el flasheo falla por timing o no entra en modo descarga:
1. Desconecta el USB.
2. **Mantén pulsado BOOT** (botón cerca del USB).
3. Conecta el USB sin soltar BOOT.
4. Suelta BOOT. El chip está en download mode.
5. Reintenta el script.

> Tras el flasheo del primer firmware multi-página, **se pierde la config previa de los botones** (porque las claves NVS cambian). Los iconos siempre se pierden al reiniciar (no se guardan en NVS).

## Recompilar el firmware

Solo necesario si modificas `button_counter/button_counter.ino`.

```bash
# Toolchain (descarga inicial ~600 MB, no toca el sistema)
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh \
    | BINDIR=$HOME/.local/bin sh
export PATH=$HOME/.local/bin:$PATH

arduino-cli config init --overwrite
arduino-cli config add board_manager.additional_urls \
    https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@2.0.17
arduino-cli lib install "LovyanGFX@1.2.19"
arduino-cli lib install "NimBLE-Arduino@2.4.0"

# La librería BLE-Keyboard del fork wakwak-koba (compatible con NimBLE 2.x)
git clone https://github.com/wakwak-koba/ESP32-BLE-Keyboard.git \
    ~/Arduino/libraries/ESP32-BLE-Keyboard

# Compilar
arduino-cli compile \
    --fqbn "esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,FlashMode=qio,PartitionScheme=default_8MB,UploadSpeed=460800" \
    --build-path /tmp/streamdeck-build \
    button_counter/

# Copiar binarios al firmware/ y flashear
cp /tmp/streamdeck-build/button_counter.ino*.bin firmware/
./firmware/flashear_linux.sh /dev/ttyUSB0
```

## Configuración persistente

| Archivo | Qué guarda |
|---------|-----------|
| `~/.config/diy-streamdeck/settings.json` | Nombres de páginas (ampliable a más opciones). |
| `~/.config/diy-streamdeck/icons/p<page>_b<idx>.png` | Caché local de iconos por botón. |
| NVS del ESP32 (namespace `deck`) | Etiqueta/color/acción/etc. de los 36 botones + brillo. |

Para borrar todo:

```bash
rm -rf ~/.config/diy-streamdeck
# Y en el deck: edita los botones y dale al botón "Limpiar" en cada uno,
# o reflashea para volver a defaults.
```

## Resolución de problemas

### La app dice "Desconectado" y no encuentra el deck

```bash
ls /dev/ttyUSB* /dev/ttyACM*       # ¿está el dispositivo?
groups | grep dialout              # ¿estás en el grupo?
sudo dmesg --since "1 minute ago"  # ¿qué dice el kernel?
```

Si ves `usb 1-1: ch341-uart converter now attached to ttyUSB0` está bien y es problema de permisos (cierra sesión tras `usermod -aG dialout`).

### Los atajos de teclado no funcionan

```bash
ls -l /dev/uinput          # debe ser crw-rw---- root input
groups | grep input        # debes estar en input
```

Si todo OK, mira el log al lanzar: `streamdeck` por terminal y verás `[keyboard] virtual uinput keyboard ready`.

Si dice `sin permiso para /dev/uinput`, vuelve a entrar en sesión tras `sudo usermod -aG input $USER`.

### El icono del dock muestra "python3" o el icono genérico

```bash
./linux/uninstall.sh
./linux/install.sh
# Cierra sesión y vuelve a entrar para que GNOME refresque caches.
```

### Los iconos no se actualizan al cambiar el tamaño

Esto era un bug; reinstala la app (`./linux/install.sh`) para asegurar la versión actual. Si pasa de nuevo, abre un issue.

### El swipe no detecta bien

El umbral son 80 px de movimiento horizontal y máximo 60 px vertical. Si tu placa lleva un overlay táctil distinto puede que necesite ajuste. Ver `SWIPE_DX` y `SWIPE_MAX_DY` en `button_counter/button_counter.ino`.

## Diferencias con el upstream

| Tema | Upstream `sintex85` | Este fork |
|------|---------------------|-----------|
| OS objetivo | Mac / Windows | Linux (GNOME Wayland probado) |
| Cliente PC | Web (`docs/index.html`) en Chrome | App GTK4 nativa (`linux/streamdeck.py`) |
| Páginas | 1 (12 botones) | 3 (36 botones) |
| Cambio de página | — | Swipe + flechas + click en pestañas |
| Atajos teclado | BLE (vía `KEY_LEFT_GUI` orientado Mac) | uinput desde el PC + presets GNOME |
| URL/App | Chrome JS abre la pestaña | `xdg-open` desde la GUI |
| Protocolo serial | `BTN:idx:type:action` | `BTN:page:idx:type:action` |
| Iconos | Persisten en RAM hasta reinicio | Idem; caché local en disco para resend automático |
| Bluetooth | Necesario para teclado | Opcional (fallback) |
| Tray icon | — | Pendiente (problema GTK3/GTK4 con AyatanaAppIndicator) |

## Estructura del repo

```
diy-streamdeck/
├── README.md                    ← este archivo
├── CLAUDE.md                    ← notas técnicas para agentes/devs
├── button_counter/
│   ├── button_counter.ino       ← firmware Arduino
│   └── LGFX_ESP32S3_RGB_*.h     ← config display LovyanGFX
├── firmware/
│   ├── boot_app0.bin            ← stage 0 bootloader
│   ├── button_counter.ino.bin   ← app
│   ├── button_counter.ino.bootloader.bin
│   ├── button_counter.ino.partitions.bin
│   └── flashear_linux.sh        ← script wrapper de esptool
└── linux/
    ├── streamdeck.py            ← app GTK4 (~1k líneas, single-file)
    ├── icon.svg                 ← icono de la app
    ├── install.sh               ← instalador en ~/.local
    └── uninstall.sh
```

## Créditos y licencia

Hardware y diseño original: **Bits y Tornillos** ([@sintex85](https://github.com/sintex85)).

Fork Linux y app GTK4: [@gorkaFM](https://github.com/gorkaFM).

Librerías:
- [LovyanGFX](https://github.com/lovyan03/LovyanGFX) — driver de la pantalla.
- [NimBLE-Arduino](https://github.com/h2zero/NimBLE-Arduino) — stack BLE.
- [ESP32-BLE-Keyboard (fork wakwak-koba)](https://github.com/wakwak-koba/ESP32-BLE-Keyboard) — perfil HID.
- [python-evdev](https://github.com/gvalkov/python-evdev) — uinput.
- GTK4 + libadwaita — GUI.

Sin licencia explícita declarada por el upstream. Asumo "uso personal / educativo"; verifica antes de redistribuir.
