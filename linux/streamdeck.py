#!/usr/bin/env python3
"""DIY Stream Deck - Linux GUI

Native GTK4 app for the ESP32-8048S043 Stream Deck. Replaces the web-based
config tool with a Linux-native app that handles URL/app launching via
xdg-open and lives in the system tray.
"""
import argparse
import base64
import glob
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio, GObject, Adw  # noqa: E402

# AyatanaAppIndicator3 pulls GTK3, which conflicts with our GTK4 in-process.
# Disabled by default; the tray runs as a separate subprocess if requested.
HAS_TRAY = False
AppIndicator = None

import serial  # noqa: E402
from PIL import Image  # noqa: E402

try:
    import evdev
    from evdev import UInput, ecodes as ec
    HAS_EVDEV = True
except ImportError:
    HAS_EVDEV = False
    ec = None

# ─── Constants ───
APP_ID = "com.bitsytornillos.streamdeck"
NUM_PAGES = 3
NUM_BUTTONS = 12
COLS, ROWS = 4, 3
ICON_SIZES = [24, 32, 48, 64]
PORT_GLOBS = ["/dev/ttyUSB*", "/dev/ttyACM*"]
BAUD = 115200

CONFIG_DIR = Path.home() / ".config" / "diy-streamdeck"
ICON_CACHE = CONFIG_DIR / "icons"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
RESOURCE_DIR = Path(__file__).resolve().parent
ICON_PATH = RESOURCE_DIR / "icon.svg"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
ICON_CACHE.mkdir(parents=True, exist_ok=True)

DEFAULT_COLORS = [
    (231, 76, 60), (46, 204, 113), (52, 152, 219), (241, 196, 15),
    (155, 89, 182), (230, 126, 34), (26, 188, 156), (236, 64, 122),
    (52, 73, 94), (127, 140, 141), (39, 174, 96), (41, 128, 185),
]

ACTION_TYPE_NAMES = {0: "Ninguna", 1: "URL", 2: "Teclado", 3: "App", 4: "Texto"}

KEYBOARD_GROUPS = [
    ("GNOME / Ubuntu", [
        ("🖥 Terminal", "ctrl+alt+t"),
        ("🪟 Cambiar ventana", "alt+tab"),
        ("✖ Cerrar ventana", "alt+f4"),
        ("🔒 Bloquear pantalla", "super+l"),
        ("🗖 Maximizar", "super+up"),
        ("🗗 Restaurar/min", "super+down"),
        ("◀ Tile izquierda", "super+left"),
        ("▶ Tile derecha", "super+right"),
        ("⛶ Pantalla completa", "f11"),
        ("⬇ Workspace siguiente", "ctrl+alt+down"),
        ("⬆ Workspace anterior", "ctrl+alt+up"),
        ("🚀 Vista de Apps", "super+a"),
        ("📷 Captura pantalla", "printscreen"),
    ]),
    ("Edición", [
        ("📋 Copiar", "ctrl+c"),
        ("📌 Pegar", "ctrl+v"),
        ("✂ Cortar", "ctrl+x"),
        ("↩ Deshacer", "ctrl+z"),
        ("↪ Rehacer", "ctrl+shift+z"),
        ("☰ Seleccionar todo", "ctrl+a"),
        ("💾 Guardar", "ctrl+s"),
        ("🔍 Buscar", "ctrl+f"),
        ("🖨 Imprimir", "ctrl+p"),
    ]),
    ("Navegador", [
        ("🆕 Nueva pestaña", "ctrl+t"),
        ("✖ Cerrar pestaña", "ctrl+w"),
        ("↻ Reabrir pestaña", "ctrl+shift+t"),
        ("🔄 Recargar", "ctrl+r"),
        ("◀ Atrás", "alt+left"),
        ("▶ Adelante", "alt+right"),
        ("🔧 DevTools", "ctrl+shift+i"),
    ]),
    ("Multimedia", [
        ("🔊 Vol +", "vol_up"),
        ("🔉 Vol -", "vol_down"),
        ("🔇 Silenciar", "vol_mute"),
        ("⏯ Play/Pause", "play_pause"),
        ("⏭ Siguiente", "next_track"),
        ("⏮ Anterior", "prev_track"),
    ]),
]

APP_PRESETS = [
    ("🎵 Spotify", "spotify:"),
    ("💬 Discord", "discord:"),
    ("💼 Slack", "slack:"),
    ("📹 Zoom", "zoommtg:"),
    ("✈ Telegram", "tg:"),
    ("🎮 Steam", "steam://open/main"),
    ("📧 Mail", "mailto:"),
    ("📁 Archivos", "file:///home/" + os.environ.get("USER", "")),
    ("🎬 Netflix", "https://www.netflix.com"),
    ("📺 YouTube", "https://www.youtube.com"),
    ("🛒 Amazon", "https://www.amazon.es"),
    ("🌐 Wikipedia", "https://es.wikipedia.org"),
]


# ─── Data ───
@dataclass
class ButtonData:
    label: str = ""
    r: int = 100
    g: int = 100
    b: int = 100
    action: str = ""
    actionType: int = 0
    iconSizeIdx: int = 1
    borderStyle: int = 0
    showLabel: bool = True
    hasIcon: bool = False  # whether the device currently has the icon loaded

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        b = ButtonData()
        for k, v in d.items():
            if hasattr(b, k):
                setattr(b, k, v)
        return b


def default_button(idx: int) -> ButtonData:
    r, g, b = DEFAULT_COLORS[idx % 12]
    return ButtonData(label=str(idx + 1), r=r, g=g, b=b)


# ─── User settings ───
def default_page_names() -> list[str]:
    return [f"Página {i + 1}" for i in range(NUM_PAGES)]


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(data: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"settings save failed: {e}", file=sys.stderr)


def get_page_names() -> list[str]:
    s = load_settings()
    names = s.get("page_names")
    if isinstance(names, list) and len(names) == NUM_PAGES and all(isinstance(n, str) for n in names):
        return [n.strip() or f"Página {i+1}" for i, n in enumerate(names)]
    return default_page_names()


def set_page_names(names: list[str]):
    s = load_settings()
    s["page_names"] = [n.strip()[:32] or f"Página {i+1}" for i, n in enumerate(names)]
    save_settings(s)


# ─── Icon helpers ───
def img_to_rgb565_b64(path: Path, size: int, bg: tuple) -> str:
    """Open image, resize to size×size compositing over bg, return base64 RGB565 BE."""
    img = Image.open(path)
    canvas = Image.new("RGB", (size, size), bg)
    if img.mode in ("RGBA", "LA"):
        scaled = img.convert("RGBA").resize((size, size), Image.LANCZOS)
        canvas.paste(scaled, (0, 0), scaled)
    else:
        canvas.paste(img.convert("RGB").resize((size, size), Image.LANCZOS), (0, 0))
    pixels = list(canvas.getdata())
    out = bytearray(size * size * 2)
    for i, (r, g, b) in enumerate(pixels):
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out[i * 2] = (v >> 8) & 0xFF
        out[i * 2 + 1] = v & 0xFF
    return base64.b64encode(bytes(out)).decode()


def icon_cache_path(page: int, idx: int) -> Path:
    return ICON_CACHE / f"p{page}_b{idx}.png"


# ─── Serial link ───
class SerialLink:
    """Background serial reader/writer with auto-detect and reconnect."""

    def __init__(self, on_line, on_connect_change):
        self.on_line = on_line                  # callable(line: str), called on main thread
        self.on_connect_change = on_connect_change  # callable(connected: bool, port: str|None)
        self.port = None
        self.port_name = None
        self.connected = False
        self.running = True
        self.write_q: queue.Queue = queue.Queue()
        self._connect_lock = threading.Lock()
        self._buf = b""

    def start(self):
        threading.Thread(target=self._reader, daemon=True, name="sd-reader").start()
        threading.Thread(target=self._writer, daemon=True, name="sd-writer").start()

    def stop(self):
        self.running = False
        self._disconnect()

    def write(self, cmd: str):
        self.write_q.put(("line", cmd))

    def write_chunked(self, cmd: str, chunk_size: int = 512, delay: float = 0.02):
        self.write_q.put(("chunked", cmd, chunk_size, delay))

    def _try_connect(self):
        candidates = []
        for g in PORT_GLOBS:
            candidates.extend(glob.glob(g))
        candidates.sort()
        for path in candidates:
            try:
                with self._connect_lock:
                    p = serial.Serial(path, BAUD, timeout=0.3, write_timeout=2.0)
                    self.port = p
                    self.port_name = path
                    self.connected = True
                    self._buf = b""
                GLib.idle_add(self.on_connect_change, True, path)
                return True
            except (serial.SerialException, OSError):
                continue
        return False

    def _disconnect(self):
        with self._connect_lock:
            if self.port:
                try:
                    self.port.close()
                except Exception:
                    pass
            self.port = None
            self.port_name = None
            was = self.connected
            self.connected = False
        if was:
            GLib.idle_add(self.on_connect_change, False, None)

    def _reader(self):
        backoff = 0
        while self.running:
            if not self.connected:
                if self._try_connect():
                    backoff = 0
                else:
                    time.sleep(min(0.5 + backoff * 0.5, 3))
                    backoff += 1
                    continue
            try:
                with self._connect_lock:
                    p = self.port
                if not p:
                    continue
                data = p.read(2048)
                if not data:
                    continue
                self._buf += data
                while b"\n" in self._buf:
                    raw, self._buf = self._buf.split(b"\n", 1)
                    line = raw.decode(errors="ignore").strip("\r\n ")
                    if line:
                        GLib.idle_add(self.on_line, line)
            except (serial.SerialException, OSError):
                self._disconnect()
            except Exception as e:
                print(f"[serial reader] {e}", file=sys.stderr)
                self._disconnect()

    def _writer(self):
        while self.running:
            try:
                item = self.write_q.get(timeout=0.3)
            except queue.Empty:
                continue
            if not self.connected or not self.port:
                continue
            try:
                with self._connect_lock:
                    if not self.port:
                        continue
                    if item[0] == "line":
                        self.port.write((item[1] + "\n").encode())
                    elif item[0] == "chunked":
                        _, payload, chunk, delay = item
                        full = (payload + "\n").encode()
                        for i in range(0, len(full), chunk):
                            self.port.write(full[i : i + chunk])
                            self.port.flush()
                            if i + chunk < len(full):
                                time.sleep(delay)
            except (serial.SerialException, OSError):
                self._disconnect()


# ─── Keyboard injection (USB-only mode via /dev/uinput) ───
class KeyboardInjector:
    """Virtual keyboard via /dev/uinput. Lets us run keyboard shortcuts and
    text typing on Wayland/X11 without depending on the device's BLE keyboard."""

    @staticmethod
    def _build_keymap():
        if not HAS_EVDEV:
            return {}
        m = {
            "ctrl": ec.KEY_LEFTCTRL, "control": ec.KEY_LEFTCTRL,
            "shift": ec.KEY_LEFTSHIFT,
            "alt": ec.KEY_LEFTALT, "option": ec.KEY_LEFTALT,
            "super": ec.KEY_LEFTMETA, "win": ec.KEY_LEFTMETA,
            "gui": ec.KEY_LEFTMETA, "meta": ec.KEY_LEFTMETA,
            "cmd": ec.KEY_LEFTMETA, "command": ec.KEY_LEFTMETA,
            "enter": ec.KEY_ENTER, "return": ec.KEY_ENTER,
            "esc": ec.KEY_ESC, "escape": ec.KEY_ESC,
            "tab": ec.KEY_TAB, "space": ec.KEY_SPACE,
            "backspace": ec.KEY_BACKSPACE, "delete": ec.KEY_DELETE,
            "up": ec.KEY_UP, "down": ec.KEY_DOWN,
            "left": ec.KEY_LEFT, "right": ec.KEY_RIGHT,
            "home": ec.KEY_HOME, "end": ec.KEY_END,
            "pageup": ec.KEY_PAGEUP, "pagedown": ec.KEY_PAGEDOWN,
            "insert": ec.KEY_INSERT,
            "printscreen": ec.KEY_SYSRQ, "prtsc": ec.KEY_SYSRQ,
            "vol_up": ec.KEY_VOLUMEUP,
            "vol_down": ec.KEY_VOLUMEDOWN,
            "vol_mute": ec.KEY_MUTE,
            "play_pause": ec.KEY_PLAYPAUSE,
            "next_track": ec.KEY_NEXTSONG,
            "prev_track": ec.KEY_PREVIOUSSONG,
        }
        for c in "abcdefghijklmnopqrstuvwxyz":
            m[c] = getattr(ec, f"KEY_{c.upper()}")
        for d in range(10):
            m[str(d)] = getattr(ec, f"KEY_{d}")
        for i in range(1, 13):
            m[f"f{i}"] = getattr(ec, f"KEY_F{i}")
        return m

    KEY_MAP = None  # filled in __init__ once HAS_EVDEV is verified

    # Symbols on US layout
    UNSHIFTED_SYMBOLS = None
    SHIFTED_PAIRS = {
        "!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
        "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
        "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\",
        ":": ";", '"': "'", "<": ",", ">": ".", "?": "/", "~": "`",
    }

    def __init__(self):
        self.ui = None
        self.error = None
        if not HAS_EVDEV:
            self.error = "python3-evdev no instalado"
            return
        if KeyboardInjector.KEY_MAP is None:
            KeyboardInjector.KEY_MAP = self._build_keymap()
            KeyboardInjector.UNSHIFTED_SYMBOLS = {
                "-": ec.KEY_MINUS, "=": ec.KEY_EQUAL,
                "[": ec.KEY_LEFTBRACE, "]": ec.KEY_RIGHTBRACE,
                "\\": ec.KEY_BACKSLASH, ";": ec.KEY_SEMICOLON,
                "'": ec.KEY_APOSTROPHE, ",": ec.KEY_COMMA,
                ".": ec.KEY_DOT, "/": ec.KEY_SLASH, "`": ec.KEY_GRAVE,
            }
        try:
            keys = set(self.KEY_MAP.values())
            keys.update(self.UNSHIFTED_SYMBOLS.values())
            cap = {ec.EV_KEY: list(keys)}
            self.ui = UInput(cap, name="DIY-StreamDeck-Virtual-KB", version=0x1)
        except PermissionError as e:
            self.error = f"sin permiso para /dev/uinput ({e}); añade tu usuario al grupo input"
        except Exception as e:
            self.error = f"uinput init falló: {e}"

    @property
    def available(self) -> bool:
        return self.ui is not None

    def send_combo(self, combo: str) -> bool:
        if not self.ui:
            return False
        s = combo.lower().strip()
        if not s:
            return False
        # Single-token (media key, F-key, plain letter)
        if "+" not in s and s in self.KEY_MAP:
            self._press_release([self.KEY_MAP[s]])
            return True
        parts = [p.strip() for p in s.split("+") if p.strip()]
        if not parts:
            return False
        codes = []
        for p in parts:
            if p in self.KEY_MAP:
                codes.append(self.KEY_MAP[p])
            else:
                print(f"[combo] desconocido: '{p}' en '{combo}'", file=sys.stderr)
                return False
        self._press_release(codes)
        return True

    def type_text(self, text: str) -> bool:
        if not self.ui:
            return False
        for ch in text:
            self._type_char(ch)
            time.sleep(0.005)
        return True

    def _press_release(self, codes):
        for c in codes:
            self.ui.write(ec.EV_KEY, c, 1)
        self.ui.syn()
        time.sleep(0.02)
        for c in reversed(codes):
            self.ui.write(ec.EV_KEY, c, 0)
        self.ui.syn()

    def _type_char(self, ch: str):
        if ch == " ":
            self._press_release([ec.KEY_SPACE]); return
        if ch == "\n":
            self._press_release([ec.KEY_ENTER]); return
        if ch == "\t":
            self._press_release([ec.KEY_TAB]); return
        if ch.isalpha() and ch.isascii():
            k = getattr(ec, f"KEY_{ch.upper()}", None)
            if k is None: return
            if ch.isupper():
                self._press_release([ec.KEY_LEFTSHIFT, k])
            else:
                self._press_release([k])
            return
        if ch.isdigit():
            k = getattr(ec, f"KEY_{ch}", None)
            if k: self._press_release([k])
            return
        if ch in self.SHIFTED_PAIRS:
            base = self.SHIFTED_PAIRS[ch]
            if base.isdigit():
                k = getattr(ec, f"KEY_{base}")
            elif base in self.UNSHIFTED_SYMBOLS:
                k = self.UNSHIFTED_SYMBOLS[base]
            else:
                return
            self._press_release([ec.KEY_LEFTSHIFT, k])
            return
        if ch in self.UNSHIFTED_SYMBOLS:
            self._press_release([self.UNSHIFTED_SYMBOLS[ch]])
            return
        # Fallback for non-mapped chars: ignore (ASCII-only US layout)

    def close(self):
        if self.ui:
            try:
                self.ui.close()
            except Exception:
                pass
            self.ui = None


_kb_injector: KeyboardInjector | None = None

def get_kb() -> KeyboardInjector:
    global _kb_injector
    if _kb_injector is None:
        _kb_injector = KeyboardInjector()
        if _kb_injector.error:
            print(f"[keyboard] {_kb_injector.error}", file=sys.stderr)
        else:
            print("[keyboard] virtual uinput keyboard ready", file=sys.stderr)
    return _kb_injector


# ─── Action handler ───
def execute_action(action_type: int, action: str):
    """Run an action received from the deck (URL/App via xdg-open, keyboard/text via uinput)."""
    if not action:
        return
    if action_type in (1, 3):
        try:
            subprocess.Popen(
                ["xdg-open", action],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print("xdg-open not found", file=sys.stderr)
    elif action_type == 2:
        kb = get_kb()
        if kb.available:
            kb.send_combo(action)
        else:
            print(f"[keyboard] no disponible: {kb.error}", file=sys.stderr)
    elif action_type == 4:
        kb = get_kb()
        if kb.available:
            kb.type_text(action)


# ─── Style manager ───
class StyleManager:
    """Single global CSS provider; we add per-button color rules dynamically."""

    BASE_CSS = """
    .deck-card {
        border-radius: 14px;
        min-width: 120px;
        min-height: 90px;
        padding: 6px;
        color: white;
        font-weight: 600;
        border: 2px solid transparent;
        background-image: none;
    }
    .deck-card:hover {
        border-color: rgba(255,255,255,0.45);
    }
    .deck-card .deck-label {
        text-shadow: 0 1px 2px rgba(0,0,0,0.6);
        font-size: 13px;
    }
    .deck-card .deck-hint {
        font-size: 10px;
        opacity: 0.75;
    }
    .deck-grid {
        padding: 12px;
    }
    .status-pill {
        padding: 2px 10px;
        border-radius: 10px;
        font-size: 11px;
    }
    .status-on { background-color: #0d3320; color: #4ade80; }
    .status-off { background-color: #3b1111; color: #f87171; }
    """

    def __init__(self):
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self.provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 100,
        )
        self.colors = {}
        self._load()

    def set_color(self, key: str, r: int, g: int, b: int):
        self.colors[key] = (r, g, b)
        self._load()

    def _load(self):
        out = [self.BASE_CSS]
        for key, (r, g, b) in self.colors.items():
            out.append(f".{key} {{ background-color: rgb({r},{g},{b}); }}")
        css = "\n".join(out)
        try:
            self.provider.load_from_string(css)
        except AttributeError:
            self.provider.load_from_data(css.encode())


# ─── Deck button widget ───
class DeckButton(Gtk.Button):
    __gtype_name__ = "DeckButton"

    def __init__(self, page: int, idx: int, on_click, style_mgr: StyleManager):
        super().__init__()
        self.page = page
        self.idx = idx
        self._style = style_mgr
        self._color_class = f"deck-p{page}-i{idx}"
        self.add_css_class("deck-card")
        self.add_css_class(self._color_class)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_size_request(140, 100)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        self.icon_widget = Gtk.Image()
        self.icon_widget.set_pixel_size(36)
        self.icon_widget.set_visible(False)
        self.label_widget = Gtk.Label()
        self.label_widget.add_css_class("deck-label")
        self.hint_widget = Gtk.Label()
        self.hint_widget.add_css_class("deck-hint")
        self.hint_widget.set_ellipsize(2)  # Pango.EllipsizeMode.MIDDLE
        self.hint_widget.set_max_width_chars(18)
        box.append(self.icon_widget)
        box.append(self.label_widget)
        box.append(self.hint_widget)
        self.set_child(box)

        self.connect("clicked", lambda *_: on_click(page, idx))
        self.update(default_button(idx))

    def update(self, data: ButtonData):
        self._style.set_color(self._color_class, data.r, data.g, data.b)
        self.label_widget.set_label(data.label or str(self.idx + 1))

        # Hint = action preview
        hint = ""
        if data.actionType == 1 and data.action:
            hint = data.action.replace("https://", "").replace("http://", "")[:30]
        elif data.actionType == 3 and data.action:
            hint = data.action[:30]
        elif data.actionType == 2 and data.action:
            hint = "⌨ " + data.action[:25]
        elif data.actionType == 4 and data.action:
            hint = "✎ " + data.action[:25]
        self.hint_widget.set_label(hint)

        # Icon: prefer cached image
        ic_path = icon_cache_path(self.page, self.idx)
        if ic_path.exists():
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(str(ic_path), 40, 40)
                self.icon_widget.set_from_pixbuf(pb)
                self.icon_widget.set_visible(True)
                return
            except GLib.Error:
                pass
        self.icon_widget.set_visible(False)


# ─── Edit dialog ───
class EditDialog(Adw.Window):
    def __init__(self, parent_window, page: int, idx: int, data: ButtonData, on_save, on_clear):
        super().__init__()
        self.page = page
        self.idx = idx
        self.data = data
        self.on_save = on_save
        self.on_clear = on_clear
        self.pending_icon_path: Path | None = None

        self.set_title(f"Botón {idx + 1} — página {page + 1}")
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_default_size(640, 760)
        self.set_size_request(480, 540)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        page_box = Adw.PreferencesPage()
        scrolled.set_child(page_box)
        toolbar.set_content(scrolled)

        # Group: basics
        g_basic = Adw.PreferencesGroup(title="Aspecto")
        page_box.add(g_basic)

        self.label_row = Adw.EntryRow(title="Etiqueta")
        self.label_row.set_text(data.label)
        g_basic.add(self.label_row)

        self.color_row = Adw.ActionRow(title="Color")
        self.color_btn = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = data.r / 255, data.g / 255, data.b / 255, 1.0
        self.color_btn.set_rgba(rgba)
        self.color_btn.set_valign(Gtk.Align.CENTER)
        self.color_row.add_suffix(self.color_btn)
        g_basic.add(self.color_row)

        # Group: action
        g_act = Adw.PreferencesGroup(title="Acción")
        page_box.add(g_act)

        self.type_row = Adw.ComboRow(title="Tipo")
        type_model = Gtk.StringList.new(list(ACTION_TYPE_NAMES.values()))
        self.type_row.set_model(type_model)
        self.type_row.set_selected(data.actionType)
        self.type_row.connect("notify::selected", lambda *_: self._refresh_action())
        g_act.add(self.type_row)

        self.action_row = Adw.EntryRow(title="Valor")
        self.action_row.set_text(data.action)
        g_act.add(self.action_row)

        self.action_help_row = Adw.ActionRow()
        self.action_help_row.add_css_class("dim-label")
        self.action_help_row.set_subtitle("")
        g_act.add(self.action_help_row)

        # Group: icon
        g_icon = Adw.PreferencesGroup(title="Icono")
        page_box.add(g_icon)

        self.icon_row = Adw.ActionRow(title="Imagen")
        ic_path = icon_cache_path(page, idx)
        self.icon_row.set_subtitle(ic_path.name if ic_path.exists() else "ninguna")
        upload_btn = Gtk.Button.new_with_label("Subir…")
        upload_btn.add_css_class("suggested-action")
        upload_btn.set_valign(Gtk.Align.CENTER)
        upload_btn.connect("clicked", self._on_upload)
        self.icon_row.add_suffix(upload_btn)
        favicon_btn = Gtk.Button.new_with_label("🌐 Favicon")
        favicon_btn.set_valign(Gtk.Align.CENTER)
        favicon_btn.set_tooltip_text("Descarga el favicon de la URL del campo Valor")
        favicon_btn.connect("clicked", self._on_favicon_btn)
        self.icon_row.add_suffix(favicon_btn)
        remove_btn = Gtk.Button.new_with_label("Quitar")
        remove_btn.set_valign(Gtk.Align.CENTER)
        remove_btn.connect("clicked", self._on_remove_icon)
        self.icon_row.add_suffix(remove_btn)
        g_icon.add(self.icon_row)

        # Presets — populated dynamically by _refresh_action.
        self.presets_group = Adw.PreferencesGroup(title="Presets")
        page_box.add(self.presets_group)
        self._presets_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        preset_row = Adw.PreferencesRow()
        preset_row.set_child(self._presets_box)
        preset_row.set_activatable(False)
        self.presets_group.add(preset_row)

        # Group: advanced (collapsible)
        g_advanced = Adw.PreferencesGroup()
        page_box.add(g_advanced)

        self.advanced_expander = Adw.ExpanderRow(title="Avanzado")
        self.advanced_expander.set_subtitle("Mostrar texto · tamaño del icono · marco")
        self.advanced_expander.set_expanded(False)
        g_advanced.add(self.advanced_expander)

        self.show_label_row = Adw.SwitchRow(title="Mostrar texto sobre el botón")
        self.show_label_row.set_active(data.showLabel)
        self.advanced_expander.add_row(self.show_label_row)

        self.size_row = Adw.ComboRow(title="Tamaño del icono")
        self.size_row.set_model(Gtk.StringList.new(["S (24 px)", "M (32 px)", "L (48 px)", "XL (64 px)"]))
        self.size_row.set_selected(data.iconSizeIdx)
        self.advanced_expander.add_row(self.size_row)

        self.border_row = Adw.ComboRow(title="Marco")
        self.border_row.set_model(Gtk.StringList.new(["Ninguno", "Fino", "Grueso", "Brillo"]))
        self.border_row.set_selected(data.borderStyle)
        self.advanced_expander.add_row(self.border_row)

        # Bottom action bar
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_margin_top(12)
        actions.set_margin_bottom(12)
        actions.set_margin_start(12)
        actions.set_margin_end(12)
        actions.set_homogeneous(True)
        cancel_btn = Gtk.Button.new_with_label("Cancelar")
        cancel_btn.connect("clicked", lambda *_: self.close())
        clear_btn = Gtk.Button.new_with_label("Limpiar")
        clear_btn.add_css_class("destructive-action")
        clear_btn.connect("clicked", self._on_clear)
        save_btn = Gtk.Button.new_with_label("Guardar")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        actions.append(cancel_btn)
        actions.append(clear_btn)
        actions.append(save_btn)
        toolbar.add_bottom_bar(actions)

        self.set_content(toolbar)

        self._refresh_action()

    def _refresh_action(self):
        t = self.type_row.get_selected()
        helps = {
            0: "Sin acción",
            1: "URL completa. Si guardas sin icono se intentará bajar el favicon.",
            2: "Atajo: ctrl+c, super+up, ctrl+alt+t, vol_up, play_pause…",
            3: "Protocolo de app: spotify:, discord:, slack:, file://…",
            4: "Texto que se escribirá vía Bluetooth",
        }
        self.action_help_row.set_subtitle(helps.get(t, ""))

        # Clear preset box children
        child = self._presets_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._presets_box.remove(child)
            child = nxt

        if t == 2:
            self.presets_group.set_visible(True)
            for group_name, items in KEYBOARD_GROUPS:
                lbl = Gtk.Label(label=group_name, xalign=0.0)
                lbl.add_css_class("dim-label")
                lbl.add_css_class("heading")
                lbl.set_margin_top(4)
                self._presets_box.append(lbl)
                flow = Gtk.FlowBox()
                flow.set_selection_mode(Gtk.SelectionMode.NONE)
                flow.set_max_children_per_line(3)
                flow.set_min_children_per_line(2)
                flow.set_row_spacing(6)
                flow.set_column_spacing(6)
                flow.set_homogeneous(True)
                for label, val in items:
                    btn = Gtk.Button.new_with_label(label)
                    btn.connect("clicked", lambda b, v=val, l=label: self._apply_preset(l, v))
                    flow.append(btn)
                self._presets_box.append(flow)
        elif t == 3:
            self.presets_group.set_visible(True)
            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_max_children_per_line(3)
            flow.set_min_children_per_line(2)
            flow.set_row_spacing(6)
            flow.set_column_spacing(6)
            flow.set_homogeneous(True)
            for label, val in APP_PRESETS:
                btn = Gtk.Button.new_with_label(label)
                btn.connect("clicked", lambda b, v=val, l=label: self._apply_preset(l, v))
                flow.append(btn)
            self._presets_box.append(flow)
        else:
            self.presets_group.set_visible(False)

    def _apply_preset(self, label: str, value: str):
        # Strip emoji prefix from label for the actual button label
        clean = label.split(" ", 1)[1] if " " in label else label
        self.label_row.set_text(clean)
        self.action_row.set_text(value)

    def _on_upload(self, *_):
        dialog = Gtk.FileDialog()
        dialog.set_title("Selecciona una imagen")
        ff = Gtk.FileFilter()
        ff.set_name("Imágenes")
        for ext in ("png", "jpg", "jpeg", "webp", "bmp", "gif", "svg"):
            ff.add_pattern(f"*.{ext}")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(ff)
        dialog.set_filters(filters)
        dialog.open(self.get_root() if isinstance(self.get_root(), Gtk.Window) else None, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        try:
            f = dialog.open_finish(result)
            self.pending_icon_path = Path(f.get_path())
            self.icon_row.set_subtitle(self.pending_icon_path.name + " (sin guardar)")
        except GLib.Error:
            pass

    def _on_remove_icon(self, *_):
        ic = icon_cache_path(self.page, self.idx)
        if ic.exists():
            try:
                ic.unlink()
            except OSError:
                pass
        self.pending_icon_path = None
        self.icon_row.set_subtitle("ninguna (se quitará al guardar)")

    def _on_favicon_btn(self, *_):
        url = self.action_row.get_text().strip()
        if not url:
            self.icon_row.set_subtitle("rellena primero el campo Valor con una URL")
            return
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url if "://" in url else "https://" + url)
            host = parsed.hostname
        except Exception:
            host = None
        if not host:
            self.icon_row.set_subtitle("URL no válida")
            return
        self.icon_row.set_subtitle(f"descargando favicon de {host}…")

        def worker():
            import urllib.request
            try:
                req = urllib.request.Request(
                    f"https://www.google.com/s2/favicons?domain={host}&sz=128",
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = resp.read()
                if len(data) < 100:
                    raise RuntimeError("respuesta vacía")
                tmp = ICON_CACHE / f".tmp_dl_{self.page}_{self.idx}.png"
                tmp.write_bytes(data)
                Image.open(tmp).load()
                GLib.idle_add(self._favicon_done, tmp, host)
            except Exception as e:
                GLib.idle_add(self._favicon_failed, str(e))

        threading.Thread(target=worker, daemon=True, name="sd-favicon-dlg").start()

    def _favicon_done(self, tmp_path: Path, host: str):
        self.pending_icon_path = tmp_path
        self.icon_row.set_subtitle(f"favicon de {host} listo (sin guardar)")
        return False

    def _favicon_failed(self, err: str):
        self.icon_row.set_subtitle(f"error favicon: {err[:60]}")
        return False

    def _on_clear(self, *_):
        self.on_clear(self.page, self.idx)
        self.close()

    def _on_save(self, *_):
        rgba = self.color_btn.get_rgba()
        new = ButtonData(
            label=self.label_row.get_text(),
            r=int(round(rgba.red * 255)),
            g=int(round(rgba.green * 255)),
            b=int(round(rgba.blue * 255)),
            action=self.action_row.get_text(),
            actionType=self.type_row.get_selected(),
            iconSizeIdx=self.size_row.get_selected(),
            borderStyle=self.border_row.get_selected(),
            showLabel=self.show_label_row.get_active(),
        )
        self.on_save(self.page, self.idx, new, self.pending_icon_path)
        self.close()


# ─── Rename pages dialog ───
class RenamePagesDialog(Adw.Window):
    def __init__(self, parent_window, current_names: list[str], on_apply):
        super().__init__()
        self.set_title("Renombrar páginas")
        self.set_transient_for(parent_window)
        self.set_modal(True)
        self.set_default_size(420, 320)
        self.set_size_request(360, 280)
        self.on_apply = on_apply

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="Nombres de las páginas",
            description="Aparecen en las pestañas de la app. Máximo 32 caracteres.",
        )
        page.add(group)

        self.entries: list[Adw.EntryRow] = []
        for i, name in enumerate(current_names):
            row = Adw.EntryRow(title=f"Página {i + 1}")
            row.set_text(name)
            group.add(row)
            self.entries.append(row)

        toolbar.set_content(page)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_margin_top(12)
        actions.set_margin_bottom(12)
        actions.set_margin_start(12)
        actions.set_margin_end(12)
        actions.set_homogeneous(True)
        cancel = Gtk.Button.new_with_label("Cancelar")
        cancel.connect("clicked", lambda *_: self.close())
        reset = Gtk.Button.new_with_label("Por defecto")
        reset.connect("clicked", self._on_reset)
        save = Gtk.Button.new_with_label("Guardar")
        save.add_css_class("suggested-action")
        save.connect("clicked", self._on_save)
        actions.append(cancel)
        actions.append(reset)
        actions.append(save)
        toolbar.add_bottom_bar(actions)

        self.set_content(toolbar)

    def _on_reset(self, *_):
        for i, row in enumerate(self.entries):
            row.set_text(f"Página {i + 1}")

    def _on_save(self, *_):
        names = [row.get_text() for row in self.entries]
        self.on_apply(names)
        self.close()


# ─── Main window ───
class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, controller):
        super().__init__(application=app)
        self.app = app
        self.ctrl = controller
        self.set_title("Stream Deck")
        self.set_default_size(720, 560)

        self.style_mgr = StyleManager()
        self.buttons_widgets: list[list[DeckButton]] = []

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        # Status pill
        self.status_label = Gtk.Label(label="Desconectado")
        self.status_label.add_css_class("status-pill")
        self.status_label.add_css_class("status-off")
        header.pack_start(self.status_label)

        # Connect/disconnect button
        self.connect_btn = Gtk.Button.new_with_label("Buscar deck")
        self.connect_btn.connect("clicked", lambda *_: self.ctrl.refresh_connection())
        header.pack_start(self.connect_btn)

        # View switcher
        self.view_stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self.view_stack)
        switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)

        # Menu
        menu = Gio.Menu()
        menu.append("Renombrar páginas…", "win.rename_pages")
        menu.append("Forzar relectura del deck", "win.refresh")
        menu.append("Acerca de", "win.about")
        menu.append("Salir", "win.quit")
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)

        # Pages (3 grids)
        self.page_view_objs: list = []
        page_names = get_page_names()
        for p in range(NUM_PAGES):
            grid = Gtk.Grid()
            grid.set_row_spacing(10)
            grid.set_column_spacing(10)
            grid.add_css_class("deck-grid")
            grid.set_hexpand(True)
            grid.set_vexpand(True)
            row_widgets = []
            for i in range(NUM_BUTTONS):
                btn = DeckButton(p, i, self.ctrl.open_edit, self.style_mgr)
                grid.attach(btn, i % COLS, i // COLS, 1, 1)
                row_widgets.append(btn)
            self.buttons_widgets.append(row_widgets)
            page_obj = self.view_stack.add_titled(grid, f"page{p}", page_names[p])
            page_obj.set_icon_name("view-grid-symbolic")
            self.page_view_objs.append(page_obj)

        toolbar.set_content(self.view_stack)
        self.set_content(toolbar)

        # Actions
        ag = Gio.SimpleActionGroup()
        for name, fn in [
            ("refresh", lambda *_: self.ctrl.request_full_config()),
            ("rename_pages", lambda *_: self._open_rename_dialog()),
            ("about", lambda *_: self._show_about()),
            ("quit", lambda *_: self.app.quit()),
        ]:
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", fn)
            ag.add_action(a)
        self.insert_action_group("win", ag)

        # When page switches in GUI, sync to device
        self.view_stack.connect("notify::visible-child-name", self._on_page_changed)
        self._suppress_page_sync = False

        # Close → hide if tray exists, quit otherwise
        self.connect("close-request", self._on_close)

    def _on_close(self, *_):
        if self.app.has_tray:
            self.set_visible(False)
            return True  # don't actually close
        return False

    def _on_page_changed(self, *_):
        if self._suppress_page_sync:
            return
        name = self.view_stack.get_visible_child_name()
        if name and name.startswith("page"):
            try:
                p = int(name[4:])
            except ValueError:
                return
            self.ctrl.set_device_page(p)

    def show_page(self, page: int):
        self._suppress_page_sync = True
        self.view_stack.set_visible_child_name(f"page{page}")
        self._suppress_page_sync = False

    def update_button(self, page: int, idx: int, data: ButtonData):
        self.buttons_widgets[page][idx].update(data)

    def set_status(self, connected: bool, port: str | None):
        if connected:
            self.status_label.set_label(f"Conectado: {port}")
            self.status_label.remove_css_class("status-off")
            self.status_label.add_css_class("status-on")
            self.connect_btn.set_label("Reconectar")
        else:
            self.status_label.set_label("Desconectado")
            self.status_label.remove_css_class("status-on")
            self.status_label.add_css_class("status-off")
            self.connect_btn.set_label("Buscar deck")

    def _show_about(self):
        d = Adw.AboutDialog()
        d.set_application_name("Stream Deck")
        d.set_version("0.1")
        d.set_developer_name("Bits y Tornillos / fork Linux")
        d.set_website("https://github.com/gorkaFM/diy-streamdeck")
        d.set_comments("Control panel para el ESP32-8048S043 Stream Deck en Linux.")
        d.present(self)

    def _open_rename_dialog(self):
        current = get_page_names()
        d = RenamePagesDialog(self, current, self._apply_page_names)
        d.present()

    def _apply_page_names(self, names: list[str]):
        set_page_names(names)
        for p, page_obj in enumerate(self.page_view_objs):
            page_obj.set_title(names[p])


# ─── Tray icon ───
class TrayIcon:
    def __init__(self, on_show, on_quit, get_status):
        if not HAS_TRAY:
            self.indicator = None
            return
        icon = str(ICON_PATH) if ICON_PATH.exists() else "input-keyboard"
        self.indicator = AppIndicator.Indicator.new(
            "diy-streamdeck",
            icon,
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_title("Stream Deck")
        menu = Gtk.Menu()

        self.status_item = Gtk.MenuItem(label="…")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)
        menu.append(Gtk.SeparatorMenuItem())

        show_item = Gtk.MenuItem(label="Mostrar ventana")
        show_item.connect("activate", lambda *_: on_show())
        menu.append(show_item)

        quit_item = Gtk.MenuItem(label="Salir")
        quit_item.connect("activate", lambda *_: on_quit())
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)
        self._get_status = get_status
        GLib.timeout_add_seconds(2, self._refresh_status)

    def _refresh_status(self):
        if not self.indicator:
            return False
        connected, port = self._get_status()
        self.status_item.set_label(f"Conectado: {port}" if connected else "Desconectado")
        return True


# ─── Controller ───
class Controller:
    """Orchestrates SerialLink, model state, MainWindow and tray."""

    def __init__(self, app):
        self.app = app
        # Model: pages[3][12]
        self.pages: list[list[ButtonData]] = [
            [default_button(i) for i in range(NUM_BUTTONS)] for _ in range(NUM_PAGES)
        ]
        self.current_page = 0
        self.window: MainWindow | None = None
        self.tray: TrayIcon | None = None
        self.serial = SerialLink(self._on_line, self._on_connect_change)
        self.last_btn_event = 0.0  # debounce double execution

    # public API to GUI
    def refresh_connection(self):
        # Force reconnect
        self.serial._disconnect()

    def request_full_config(self):
        self.serial.write("GETALL")

    def open_edit(self, page: int, idx: int):
        if not self.window:
            return
        d = EditDialog(self.window, page, idx, self.pages[page][idx], self._on_edit_save, self._on_edit_clear)
        d.present()

    def set_device_page(self, page: int):
        if 0 <= page < NUM_PAGES and page != self.current_page:
            self.serial.write(f"PAGE:{page}")

    # callbacks (main thread)
    def _on_line(self, line: str):
        if line.startswith("BTN:"):
            parts = line.split(":", 4)
            # BTN:<page>:<idx>:<type>:<action>
            if len(parts) == 5:
                try:
                    page, idx, typ = int(parts[1]), int(parts[2]), int(parts[3])
                    action = parts[4]
                except ValueError:
                    return
                # Special: gear sends BTN:0:99:1:URL
                if idx == 99:
                    execute_action(typ, action)
                    return
                # Debounce: device sends BTN once per press already, but guard accidental dupes
                now = time.monotonic()
                if now - self.last_btn_event > 0.05:
                    self.last_btn_event = now
                    execute_action(typ, action)
        elif line.startswith("CFG:"):
            self._parse_cfg(line)
        elif line.startswith("CURPAGE:"):
            try:
                p = int(line[len("CURPAGE:") :])
                if 0 <= p < NUM_PAGES:
                    self.current_page = p
                    if self.window:
                        self.window.show_page(p)
            except ValueError:
                pass
        elif line.startswith("PAGE:"):
            try:
                p = int(line[len("PAGE:") :])
                if 0 <= p < NUM_PAGES:
                    self.current_page = p
                    if self.window:
                        self.window.show_page(p)
            except ValueError:
                pass
        elif line.startswith("[") or line == "OK" or line == "END":
            pass  # logs

    def _parse_cfg(self, line: str):
        """CFG:<page>:<idx>:<label>:<r,g,b>:<hasIcon>:<sz,brd,lbl>:<actionType>:<action>"""
        # Split max 8 colons (label/action may be empty)
        parts = line.split(":", 8)
        if len(parts) < 9:
            return
        try:
            page = int(parts[1])
            idx = int(parts[2])
            label = parts[3]
            r, g, b = (int(x) for x in parts[4].split(","))
            has_icon = parts[5] == "1"
            sz, brd, lbl = (int(x) for x in parts[6].split(","))
            atype = int(parts[7])
            action = parts[8]
        except (ValueError, IndexError):
            return
        if not (0 <= page < NUM_PAGES and 0 <= idx < NUM_BUTTONS):
            return
        b_data = ButtonData(
            label=label, r=r, g=g, b=b,
            action=action, actionType=atype,
            iconSizeIdx=sz, borderStyle=brd, showLabel=bool(lbl),
            hasIcon=has_icon,
        )
        self.pages[page][idx] = b_data
        if self.window:
            self.window.update_button(page, idx, b_data)

    def _on_connect_change(self, connected: bool, port: str | None):
        if self.window:
            self.window.set_status(connected, port)
        if connected:
            # Slight delay to let firmware start up
            GLib.timeout_add(600, self._on_post_connect)

    def _on_post_connect(self):
        self.request_full_config()
        # Re-send any cached icons after a brief delay
        GLib.timeout_add(1500, self._resend_cached_icons)
        return False

    def _resend_cached_icons(self):
        for p in range(NUM_PAGES):
            for i in range(NUM_BUTTONS):
                ic = icon_cache_path(p, i)
                if ic.exists():
                    self._send_icon(p, i, ic, self.pages[p][i])
        return False

    # edit dialog callbacks
    def _on_edit_save(self, page: int, idx: int, new: ButtonData, pending_icon: Path | None):
        old = self.pages[page][idx]
        # Preserve hasIcon flag for the resend decision below
        new.hasIcon = old.hasIcon
        self.pages[page][idx] = new
        if self.window:
            self.window.update_button(page, idx, new)
        # Send SET (visual)
        self.serial.write(
            f"SET:{page}:{idx}:{new.label}:{new.r},{new.g},{new.b}:"
            f"{new.iconSizeIdx},{new.borderStyle},{1 if new.showLabel else 0}"
        )
        # Send ACT (behavior)
        self.serial.write(f"ACT:{page}:{idx}:{new.actionType}:{new.action}")

        ic_path = icon_cache_path(page, idx)
        if pending_icon and pending_icon.exists():
            # New upload → cache thumbnail and send to device
            try:
                img = Image.open(pending_icon)
                img.thumbnail((128, 128), Image.LANCZOS)
                img.save(ic_path, "PNG")
            except Exception as e:
                print(f"icon cache save failed: {e}", file=sys.stderr)
            self._send_icon(page, idx, ic_path, new)
            if self.window:
                self.window.update_button(page, idx, new)
        elif ic_path.exists():
            # Existing cache: re-send if size, color, or device-side state needs refresh
            needs = (
                old.iconSizeIdx != new.iconSizeIdx
                or (old.r, old.g, old.b) != (new.r, new.g, new.b)
                or not old.hasIcon
            )
            if needs:
                self._send_icon(page, idx, ic_path, new)
        elif new.actionType == 1 and new.action.strip():
            # URL with no icon → try fetching favicon in background
            self._fetch_favicon_async(page, idx, new.action)

    def _fetch_favicon_async(self, page: int, idx: int, url: str):
        """Download a favicon for `url`, save it as the cached icon, send to device."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url if "://" in url else "https://" + url)
            host = parsed.hostname
        except Exception:
            return
        if not host:
            return

        def worker():
            import urllib.request
            fav_url = f"https://www.google.com/s2/favicons?domain={host}&sz=128"
            try:
                req = urllib.request.Request(fav_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = resp.read()
                if not data or len(data) < 100:
                    return
                tmp = ICON_CACHE / f".tmp_p{page}_b{idx}.png"
                tmp.write_bytes(data)
                # Validate by opening
                Image.open(tmp).load()
                target = icon_cache_path(page, idx)
                tmp.replace(target)
                GLib.idle_add(self._favicon_ready, page, idx)
            except Exception as e:
                print(f"favicon fetch failed for {host}: {e}", file=sys.stderr)

        threading.Thread(target=worker, daemon=True, name="sd-favicon").start()

    def _favicon_ready(self, page: int, idx: int):
        btn = self.pages[page][idx]
        ic = icon_cache_path(page, idx)
        if ic.exists():
            self._send_icon(page, idx, ic, btn)
            if self.window:
                self.window.update_button(page, idx, btn)
        return False

    def _on_edit_clear(self, page: int, idx: int):
        b = default_button(idx)
        self.pages[page][idx] = b
        ic = icon_cache_path(page, idx)
        if ic.exists():
            try:
                ic.unlink()
            except OSError:
                pass
        self.serial.write(
            f"SET:{page}:{idx}:{b.label}:{b.r},{b.g},{b.b}:"
            f"{b.iconSizeIdx},{b.borderStyle},1"
        )
        self.serial.write(f"ACT:{page}:{idx}:0:")
        self.serial.write(f"NOICON:{page}:{idx}")
        if self.window:
            self.window.update_button(page, idx, b)

    def _send_icon(self, page: int, idx: int, source_path: Path, btn: ButtonData):
        size = ICON_SIZES[btn.iconSizeIdx]
        try:
            b64 = img_to_rgb565_b64(source_path, size, (btn.r, btn.g, btn.b))
        except Exception as e:
            print(f"icon convert failed: {e}", file=sys.stderr)
            return
        cmd = f"ICON:{page}:{idx}:{size}:{b64}"
        self.serial.write_chunked(cmd, chunk_size=512, delay=0.02)
        self.pages[page][idx].hasIcon = True

    def status(self) -> tuple[bool, str | None]:
        return self.serial.connected, self.serial.port_name


# ─── Application ───
class StreamDeckApp(Adw.Application):
    def __init__(self, minimized: bool):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.minimized = minimized
        self.has_tray = HAS_TRAY
        self.controller: Controller | None = None
        self.window: MainWindow | None = None
        self.tray = None

    def do_activate(self):
        if self.window:
            self.window.present()
            return
        self.controller = Controller(self)
        self.window = MainWindow(self, self.controller)
        self.controller.window = self.window
        self.controller.serial.start()

        # Tray
        if HAS_TRAY:
            self.tray = TrayIcon(
                on_show=lambda: self.window.present(),
                on_quit=lambda: self.quit(),
                get_status=self.controller.status,
            )
            self.controller.tray = self.tray

        if not self.minimized:
            self.window.present()

    def do_shutdown(self):
        if self.controller:
            self.controller.serial.stop()
        if _kb_injector:
            _kb_injector.close()
        Adw.Application.do_shutdown(self)


# ─── Daemon mode (no GUI) ───
def run_daemon():
    """Lightweight mode: just listen for BTN messages and run xdg-open. No window, no icons."""
    pages = [[default_button(i) for i in range(NUM_BUTTONS)] for _ in range(NUM_PAGES)]
    last = [0.0]

    def on_line(line):
        if line.startswith("BTN:"):
            parts = line.split(":", 4)
            if len(parts) == 5:
                try:
                    typ = int(parts[3])
                    action = parts[4]
                except ValueError:
                    return
                now = time.monotonic()
                if now - last[0] > 0.05:
                    last[0] = now
                    execute_action(typ, action)

    def on_status(connected, port):
        msg = f"streamdeck: {'conectado a ' + port if connected else 'desconectado'}"
        print(msg, flush=True)

    link = SerialLink(on_line, on_status)
    link.start()

    # Pump GLib main loop so idle_add callbacks fire (we don't have Gtk app)
    loop = GLib.MainLoop()
    try:
        loop.run()
    except KeyboardInterrupt:
        link.stop()


# ─── Entry ───

def main():
    parser = argparse.ArgumentParser(description="DIY Stream Deck Linux client")
    parser.add_argument("--minimized", action="store_true", help="Iniciar oculto en bandeja")
    parser.add_argument("--daemon", action="store_true", help="Modo sin GUI (solo handler de URL/apps)")
    args = parser.parse_args()

    # Make the dock/taskbar show "Stream Deck" instead of "python3".
    # GLib.set_prgname controls X11 WM_CLASS and GNOME's app match heuristic.
    GLib.set_prgname(APP_ID)
    GLib.set_application_name("Stream Deck")

    if args.daemon:
        run_daemon()
        return

    app = StreamDeckApp(minimized=args.minimized)
    app.run([])


if __name__ == "__main__":
    main()
