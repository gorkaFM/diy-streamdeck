#!/usr/bin/env bash
set -euo pipefail
rm -f "$HOME/.local/bin/streamdeck"
rm -rf "$HOME/.local/share/diy-streamdeck"
rm -f "$HOME/.local/share/applications/streamdeck.desktop"
rm -f "$HOME/.config/autostart/streamdeck.desktop"
echo "✓ Stream Deck Linux GUI desinstalado."
echo "  La config en ~/.config/diy-streamdeck/ se ha conservado por si quieres reinstalar."
echo "  Bórrala manualmente si no la quieres: rm -rf ~/.config/diy-streamdeck"
