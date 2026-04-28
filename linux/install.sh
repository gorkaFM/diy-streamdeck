#!/usr/bin/env bash
# Install Stream Deck Linux GUI to ~/.local
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ID="com.bitsytornillos.streamdeck"
BIN="$HOME/.local/bin"
SHARE="$HOME/.local/share/diy-streamdeck"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"
AUTOSTART="$HOME/.config/autostart"

mkdir -p "$BIN" "$SHARE" "$APPS" "$ICONS" "$AUTOSTART"

echo "→ copiando archivos a $SHARE/"
cp "$DIR/streamdeck.py" "$SHARE/streamdeck.py"
cp "$DIR/icon.svg"      "$SHARE/icon.svg"
chmod +x "$SHARE/streamdeck.py"

echo "→ instalando icono en $ICONS/$APP_ID.svg"
cp "$DIR/icon.svg" "$ICONS/$APP_ID.svg"

echo "→ creando wrapper $BIN/streamdeck"
cat > "$BIN/streamdeck" <<EOF
#!/usr/bin/env bash
exec python3 "$SHARE/streamdeck.py" "\$@"
EOF
chmod +x "$BIN/streamdeck"

echo "→ creando launcher $APPS/$APP_ID.desktop"
cat > "$APPS/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Stream Deck
GenericName=DIY Stream Deck
Comment=Panel de control para el DIY Stream Deck (ESP32)
Exec=$BIN/streamdeck
Icon=$APP_ID
Terminal=false
Categories=Utility;
StartupNotify=true
StartupWMClass=$APP_ID
EOF

echo "→ creando autostart $AUTOSTART/$APP_ID.desktop"
cat > "$AUTOSTART/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Stream Deck
Comment=Panel de control para el DIY Stream Deck (ESP32)
Exec=$BIN/streamdeck --minimized
Icon=$APP_ID
Terminal=false
X-GNOME-Autostart-enabled=true
Categories=Utility;
EOF

# Refresh GNOME's icon and desktop databases
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS" 2>/dev/null || true
fi

# Limpia entradas viejas con el nombre antiguo
rm -f "$APPS/streamdeck.desktop" "$AUTOSTART/streamdeck.desktop"

if ! id -nG | grep -qw dialout; then
  echo "⚠  Tu usuario NO está en el grupo 'dialout'. Hazlo con:"
  echo "    sudo usermod -aG dialout \$USER"
fi
if ! id -nG | grep -qw input; then
  echo "⚠  Tu usuario NO está en el grupo 'input' (necesario para atajos via uinput):"
  echo "    sudo usermod -aG input \$USER"
fi

echo
echo "✓ Instalado. Lanza con: streamdeck"
echo "  Arrancará minimizado al iniciar sesión."
echo "  Para desinstalar: $DIR/uninstall.sh"
