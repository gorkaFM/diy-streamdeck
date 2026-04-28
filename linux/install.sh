#!/usr/bin/env bash
# Install Stream Deck Linux GUI to ~/.local
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"
SHARE="$HOME/.local/share/diy-streamdeck"
APPS="$HOME/.local/share/applications"
AUTOSTART="$HOME/.config/autostart"

mkdir -p "$BIN" "$SHARE" "$APPS" "$AUTOSTART"

echo "→ copiando archivos a $SHARE/"
cp "$DIR/streamdeck.py" "$SHARE/streamdeck.py"
cp "$DIR/icon.svg"      "$SHARE/icon.svg"
chmod +x "$SHARE/streamdeck.py"

echo "→ creando wrapper $BIN/streamdeck"
cat > "$BIN/streamdeck" <<EOF
#!/usr/bin/env bash
exec python3 "$SHARE/streamdeck.py" "\$@"
EOF
chmod +x "$BIN/streamdeck"

echo "→ creando launcher $APPS/streamdeck.desktop"
cat > "$APPS/streamdeck.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Stream Deck
Comment=Panel de control para el DIY Stream Deck (ESP32)
Exec=$BIN/streamdeck
Icon=$SHARE/icon.svg
Terminal=false
Categories=Utility;
StartupWMClass=streamdeck
EOF

echo "→ creando autostart $AUTOSTART/streamdeck.desktop"
cat > "$AUTOSTART/streamdeck.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Stream Deck
Comment=Panel de control para el DIY Stream Deck (ESP32)
Exec=$BIN/streamdeck --minimized
Icon=$SHARE/icon.svg
Terminal=false
X-GNOME-Autostart-enabled=true
Categories=Utility;
EOF

if ! id -nG | grep -qw dialout; then
  echo "⚠  Tu usuario NO está en el grupo 'dialout'. Hazlo con:"
  echo "    sudo usermod -aG dialout \$USER"
  echo "    (cierra sesión y vuelve a entrar para aplicar)"
fi

echo
echo "✓ Instalado. Lanza con: streamdeck"
echo "  Ya está configurado para arrancar minimizado al iniciar sesión."
echo "  Para desinstalar: $DIR/uninstall.sh"
