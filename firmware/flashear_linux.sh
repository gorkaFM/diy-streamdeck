#!/usr/bin/env bash
# Flash the precompiled firmware to the ESP32-S3 via esptool.
# Usage: ./flashear_linux.sh [/dev/ttyUSB0]
set -euo pipefail

PORT="${1:-/dev/ttyUSB0}"
DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v esptool >/dev/null 2>&1 && ! command -v esptool.py >/dev/null 2>&1; then
  echo "esptool no encontrado. Instala con:"
  echo "    pip3 install --user esptool"
  exit 1
fi
TOOL="esptool"
command -v esptool >/dev/null 2>&1 || TOOL="esptool.py"

if [[ ! -e "$PORT" ]]; then
  echo "Puerto $PORT no existe. Conecta el deck por USB o pasa el puerto correcto."
  echo "    ./flashear_linux.sh /dev/ttyUSB1"
  exit 1
fi

if ! id -nG | grep -qw dialout; then
  echo "⚠  No estás en el grupo 'dialout', el flasheo puede fallar."
  echo "    sudo usermod -aG dialout \$USER  (cierra sesión y vuelve a entrar)"
fi

echo "→ flasheando $PORT con $TOOL"
"$TOOL" --chip esp32s3 --port "$PORT" --baud 460800 \
  write-flash --flash-mode dio --flash-freq 80m --flash-size 16MB \
  0x0000  "$DIR/button_counter.ino.bootloader.bin" \
  0x8000  "$DIR/button_counter.ino.partitions.bin" \
  0xe000  "$DIR/boot_app0.bin" \
  0x10000 "$DIR/button_counter.ino.bin"

echo "✓ Flasheo completado. La pantalla del deck reiniciará en unos segundos."
