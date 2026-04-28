#!/usr/bin/env bash
set -euo pipefail
APP_ID="com.bitsytornillos.streamdeck"
rm -f "$HOME/.local/bin/streamdeck"
rm -rf "$HOME/.local/share/diy-streamdeck"
rm -f  "$HOME/.local/share/applications/$APP_ID.desktop"
rm -f  "$HOME/.local/share/applications/streamdeck.desktop"
rm -f  "$HOME/.config/autostart/$APP_ID.desktop"
rm -f  "$HOME/.config/autostart/streamdeck.desktop"
rm -f  "$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi
echo "✓ Stream Deck Linux GUI desinstalado."
echo "  La config en ~/.config/diy-streamdeck/ se ha conservado."
echo "  Bórrala manualmente si no la quieres: rm -rf ~/.config/diy-streamdeck"
