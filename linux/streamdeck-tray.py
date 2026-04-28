#!/usr/bin/env python3
"""Tray icon subprocess for the Stream Deck app.

Runs in a separate process to avoid the GTK3/GTK4 conflict with
AyatanaAppIndicator3 (the indicator library only exists for GTK3 and
loading it forces Gtk-3.0 in the same Python process).

Protocol: JSON-line over stdin/stdout.

Inputs (main app → tray):
  {"type":"status","connected":true,"port":"/dev/ttyUSB0"}

Outputs (tray → main app):
  {"type":"show"}   user clicked "Mostrar ventana"
  {"type":"quit"}   user clicked "Salir"
"""
import json
import sys
import threading

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk, GLib, AyatanaAppIndicator3 as AppIndicator

ICON = sys.argv[1] if len(sys.argv) > 1 else "input-keyboard"


def emit(msg: dict):
    try:
        print(json.dumps(msg), flush=True)
    except (BrokenPipeError, OSError):
        Gtk.main_quit()


class Tray:
    def __init__(self):
        self.indicator = AppIndicator.Indicator.new(
            "diy-streamdeck",
            ICON,
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Stream Deck")

        menu = Gtk.Menu()

        self.status_item = Gtk.MenuItem(label="Buscando deck…")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)
        menu.append(Gtk.SeparatorMenuItem())

        show_item = Gtk.MenuItem(label="Mostrar ventana")
        show_item.connect("activate", lambda *_: emit({"type": "show"}))
        menu.append(show_item)

        quit_item = Gtk.MenuItem(label="Salir")
        quit_item.connect("activate", lambda *_: emit({"type": "quit"}))
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

    def update_status(self, connected: bool, port: str | None):
        self.status_item.set_label(f"Conectado: {port}" if connected else "Desconectado")


def stdin_loop(tray: Tray):
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = msg.get("type")
        if t == "status":
            GLib.idle_add(tray.update_status, msg.get("connected", False), msg.get("port"))
        elif t == "quit":
            GLib.idle_add(Gtk.main_quit)
    # stdin closed → main app gone → exit
    GLib.idle_add(Gtk.main_quit)


def main():
    tray = Tray()
    threading.Thread(target=stdin_loop, args=(tray,), daemon=True).start()
    Gtk.main()


if __name__ == "__main__":
    main()
