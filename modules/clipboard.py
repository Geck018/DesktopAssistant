"""Clipboard history for Super+V.

GNOME on Wayland does not let a background app read the clipboard, so a
small Shell extension captures copies and hands them here. Super+V is a
desktop shortcut that asks the running assistant to show the popup.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

APP_DIR = Path(__file__).resolve().parent.parent
EXT_SRC = APP_DIR / "clipboard-extension"
EXT_UUID = "assistant-clipboard@quick-todo"
EXT_DIR = Path.home() / ".local/share/gnome-shell/extensions" / EXT_UUID
HIST_PATH = APP_DIR / "state" / "clipboard.json"

BUS_NAME = "local.morning.clipboard"
OBJECT_PATH = "/local/morning/clipboard"
IFACE = "local.morning.clipboard"

SHORTCUT_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
SHORTCUT_PATH = (
    "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/assistant-clipboard/"
)
SHORTCUT_COMMAND = f"{APP_DIR / 'launch-silent.sh'} --clipboard"
MAX_ITEMS = 80
MAX_CHARS = 200_000

# org.gnome.Shell.Extensions state enum
_EXT_ENABLED = 1


class History:
    def __init__(self) -> None:
        self.items: list[str] = []
        self.load()

    def load(self) -> None:
        try:
            data = json.loads(HIST_PATH.read_text(encoding="utf-8"))
            items = data.get("items", [])
            self.items = [t for t in items if isinstance(t, str) and t.strip()][:MAX_ITEMS]
        except (OSError, json.JSONDecodeError, AttributeError):
            self.items = []

    def save(self) -> None:
        HIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"items": self.items}, ensure_ascii=False, indent=2) + "\n"
        HIST_PATH.write_text(payload, encoding="utf-8")
        try:
            HIST_PATH.chmod(0o600)
        except OSError:
            pass

    def add(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        text = text.replace("\x00", "")
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]
        if self.items and self.items[0] == text:
            return False
        if text in self.items:
            self.items.remove(text)
        self.items.insert(0, text)
        del self.items[MAX_ITEMS:]
        self.save()
        return True

    def remove(self, text: str) -> None:
        if text in self.items:
            self.items.remove(text)
            self.save()

    def clear(self) -> None:
        self.items.clear()
        self.save()


def _bus():
    return Gio.bus_get_sync(Gio.BusType.SESSION, None)


def extension_state() -> int | None:
    try:
        res = _bus().call_sync(
            "org.gnome.Shell.Extensions",
            "/org/gnome/Shell/Extensions",
            "org.gnome.Shell.Extensions",
            "GetExtensionInfo",
            GLib.Variant("(s)", (EXT_UUID,)),
            GLib.VariantType.new("(a{sv})"),
            Gio.DBusCallFlags.NONE,
            3000,
            None,
        )
    except GLib.Error:
        return None
    info = res.unpack()[0]
    state = info.get("state")
    if state is None:
        return None
    return int(state)


def extension_errors() -> list[str]:
    try:
        res = _bus().call_sync(
            "org.gnome.Shell.Extensions",
            "/org/gnome/Shell/Extensions",
            "org.gnome.Shell.Extensions",
            "GetExtensionErrors",
            GLib.Variant("(s)", (EXT_UUID,)),
            GLib.VariantType.new("(as)"),
            Gio.DBusCallFlags.NONE,
            3000,
            None,
        )
    except GLib.Error:
        return []
    return list(res.unpack()[0])


def _ext_call(method: str) -> None:
    _bus().call_sync(
        "org.gnome.Shell.Extensions",
        "/org/gnome/Shell/Extensions",
        "org.gnome.Shell.Extensions",
        method,
        GLib.Variant("(s)", (EXT_UUID,)),
        None,
        Gio.DBusCallFlags.NONE,
        8000,
        None,
    )


def _remember_extension() -> None:
    """Ask GNOME to enable the extension on the next login.

    The shell only scans extension folders at startup, so a newly copied
    extension cannot be loaded until then.
    """
    settings = Gio.Settings.new("org.gnome.shell")
    enabled = list(settings.get_strv("enabled-extensions"))
    if EXT_UUID not in enabled:
        enabled.append(EXT_UUID)
        settings.set_strv("enabled-extensions", enabled)


def install_extension() -> str | None:
    """Copy the paste helper into place. Returns a note, or None when it is already live."""
    if not EXT_SRC.is_dir():
        return "clipboard extension sources missing"
    EXT_DIR.mkdir(parents=True, exist_ok=True)
    changed = False
    for name in ("extension.js", "metadata.json"):
        data = (EXT_SRC / name).read_bytes()
        target = EXT_DIR / name
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
            changed = True
    _remember_extension()
    try:
        state = extension_state()
        if changed and state == _EXT_ENABLED:
            _ext_call("ReloadExtension")
        elif state not in (None, _EXT_ENABLED):
            _ext_call("EnableExtension")
    except GLib.Error as e:
        return str(e)
    errors = extension_errors()
    if errors:
        return errors[0][:300]
    if extension_state() != _EXT_ENABLED:
        return "paste helper loads on next login"
    return None


def ensure_shortcut() -> None:
    """Bind Super+V. The notification list keeps Super+M."""
    media = Gio.Settings.new(SHORTCUT_SCHEMA)
    paths = list(media.get_strv("custom-keybindings"))
    if SHORTCUT_PATH not in paths:
        paths.append(SHORTCUT_PATH)
        media.set_strv("custom-keybindings", paths)
    custom = Gio.Settings.new_with_path(
        SHORTCUT_SCHEMA + ".custom-keybinding",
        SHORTCUT_PATH,
    )
    if custom.get_string("name") != "Clipboard history":
        custom.set_string("name", "Clipboard history")
    if custom.get_string("command") != SHORTCUT_COMMAND:
        custom.set_string("command", SHORTCUT_COMMAND)
    if custom.get_string("binding") != "<Super>v":
        custom.set_string("binding", "<Super>v")

    shell = Gio.Settings.new("org.gnome.shell.keybindings")
    binds = list(shell.get_strv("toggle-message-tray"))
    if "<Super>v" in binds:
        kept = [b for b in binds if b != "<Super>v"] or ["<Super>m"]
        shell.set_strv("toggle-message-tray", kept)


def fetch_items() -> list[str] | None:
    try:
        res = _bus().call_sync(
            BUS_NAME,
            OBJECT_PATH,
            IFACE,
            "Get",
            None,
            GLib.VariantType.new("(as)"),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
    except GLib.Error:
        return None
    return list(res.unpack()[0])


def request_paste(text: str) -> bool:
    """Copy via the shell and paste into the window that was focused before the popup."""
    try:
        _bus().call_sync(
            BUS_NAME,
            OBJECT_PATH,
            IFACE,
            "Paste",
            GLib.Variant("(s)", (text,)),
            None,
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
        return True
    except GLib.Error:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        return False


def _preview(text: str) -> str:
    one = " ".join(text.split())
    if len(one) > 90:
        return one[:89] + "…"
    return one


class ClipboardWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application, service: Service):
        super().__init__(application=application, title="Clipboard")
        self.service = service
        self.get_style_context().add_class("assistant")
        self.set_default_size(520, 460)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", self._on_delete)
        self.connect("key-press-event", self._on_key)

        header = Gtk.HeaderBar(title="Clipboard")
        header.set_show_close_button(True)
        clear = Gtk.Button.new_with_label("Clear")
        clear.get_style_context().add_class("quiet")
        clear.set_relief(Gtk.ReliefStyle.NONE)
        clear.connect("clicked", lambda *_: self._clear())
        header.pack_end(clear)
        self.set_titlebar(header)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_top(10)
        root.set_margin_bottom(10)
        root.set_margin_start(10)
        root.set_margin_end(10)
        self.add(root)

        self.search = Gtk.Entry()
        self.search.set_placeholder_text("Search copied text…")
        self.search.connect("changed", lambda *_: self.refresh())
        self.search.connect("key-press-event", self._on_key)
        root.pack_start(self.search, False, False, 0)

        self.hint = Gtk.Label(xalign=0)
        self.hint.set_line_wrap(True)
        self.hint.get_style_context().add_class("muted")
        root.pack_start(self.hint, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        root.pack_start(scroll, True, True, 0)

        self.list = Gtk.ListBox()
        self.list.get_style_context().add_class("clips")
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.connect("row-activated", self._on_row)
        scroll.add(self.list)

        self._status("")

    def _status(self, extra: str = "") -> None:
        if self.service.paste_on:
            base = "Enter pastes into the previous window · Esc closes"
        else:
            base = "Enter copies · Ctrl+V pastes · Esc closes"
        if extra:
            base = extra + " " + base
        self.hint.set_text(base)

    def _on_delete(self, *_args):
        self.hide()
        return True

    def present_popup(self) -> None:
        self.search.set_text("")
        self._status("")
        self.refresh()
        self.set_keep_above(True)
        self.show_all()
        self.present()
        self.search.grab_focus()
        GLib.timeout_add(300, self._drop_above)

    def _drop_above(self) -> bool:
        self.set_keep_above(False)
        return False

    def refresh(self) -> None:
        query = self.search.get_text().strip().lower()
        for child in list(self.list.get_children()):
            self.list.remove(child)
        shown = 0
        for text in self.service.history.items:
            if query and query not in text.lower():
                continue
            self.list.add(self._row(text))
            shown += 1
        if shown == 0:
            empty = Gtk.Label(xalign=0)
            empty.set_margin_top(12)
            empty.set_margin_start(8)
            empty.get_style_context().add_class("muted")
            empty.set_text("Nothing copied yet." if not query else "No matches.")
            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            row.add(empty)
            self.list.add(row)
        self.list.show_all()
        first = self.list.get_row_at_index(0)
        if first is not None and first.get_selectable():
            self.list.select_row(first)

    def _row(self, text: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(8)
        box.set_margin_end(4)
        label = Gtk.Label(label=_preview(text), xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_hexpand(True)
        label.set_tooltip_text(text if len(text) < 2000 else text[:2000] + "…")
        box.pack_start(label, True, True, 0)
        delete = Gtk.Button.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
        delete.set_relief(Gtk.ReliefStyle.NONE)
        delete.get_style_context().add_class("icon-quiet")
        delete.set_tooltip_text("Remove")
        delete.connect("clicked", self._on_delete_item, text)
        box.pack_end(delete, False, False, 0)
        row.add(box)
        row._clip_text = text  # type: ignore[attr-defined]
        return row

    def _on_delete_item(self, _button, text: str):
        self.service.history.remove(text)
        self.refresh()

    def _clear(self) -> None:
        self.service.history.clear()
        self.refresh()

    def _selected_text(self) -> str | None:
        row = self.list.get_selected_row()
        if row is None:
            return None
        return getattr(row, "_clip_text", None)

    def _activate_selected(self) -> None:
        text = self._selected_text()
        if text:
            self.service.pick(text)

    def _on_row(self, _box, row):
        text = getattr(row, "_clip_text", None)
        if text:
            self.service.pick(text)

    def _move(self, delta: int) -> None:
        rows = [r for r in self.list.get_children() if getattr(r, "_clip_text", None)]
        if not rows:
            return
        selected = self.list.get_selected_row()
        try:
            idx = rows.index(selected)
        except ValueError:
            idx = 0
        idx = max(0, min(len(rows) - 1, idx + delta))
        self.list.select_row(rows[idx])

    def _on_key(self, _widget, event):
        key = event.keyval
        if key == Gdk.KEY_Escape:
            self.hide()
            return True
        if key == Gdk.KEY_Down:
            self._move(1)
            return True
        if key == Gdk.KEY_Up:
            self._move(-1)
            return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._activate_selected()
            return True
        return False


class Service:
    def __init__(self) -> None:
        self.history = History()
        self.capture_on = False
        self.paste_on = False
        self._popup: ClipboardWindow | None = None
        self._app: Gtk.Application | None = None
        self._started = False
        self._watch_id = 0
        self._signal_id = 0
        self._synced = False
        self._sync_tries = 0
        self._watcher: subprocess.Popen[str] | None = None

    def start(self, app: Gtk.Application) -> None:
        if self._started:
            return
        self._started = True
        self._app = app
        from modules import state as app_state

        err = install_extension()
        if err:
            app_state.log(f"clipboard extension: {err}")
        else:
            app_state.log("clipboard extension enabled")
        self._start_x11_watcher()
        try:
            ensure_shortcut()
            app_state.log("clipboard shortcut Super+V")
        except Exception as e:
            app_state.log(f"clipboard shortcut failed: {e}")

        bus = _bus()
        self._signal_id = bus.signal_subscribe(
            BUS_NAME,
            IFACE,
            "Pushed",
            OBJECT_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_pushed,
        )
        self._watch_id = Gio.bus_watch_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameWatcherFlags.NONE,
            self._on_name,
            None,
        )
        GLib.timeout_add(400, self._sync_once)

    def _on_name(self, *_args):
        self._sync_once()

    def _sync_once(self) -> bool:
        self._sync_tries += 1
        items = fetch_items()
        if items is None:
            return self._sync_tries < 20
        self.capture_on = True
        self.paste_on = True
        # Oldest first so the newest ends up at the front.
        for text in reversed(items):
            self.history.add(text)
        self._synced = True
        if self._popup is not None and self._popup.get_visible():
            self._popup.refresh()
        return False

    def _on_pushed(self, _conn, _sender, _path, _iface, _signal, params):
        text = params.unpack()[0] if params is not None else ""
        self.capture_on = True
        self.paste_on = True
        self._ingest(text)

    def _start_x11_watcher(self) -> None:
        if self._watcher is not None and self._watcher.poll() is None:
            return
        env = os.environ.copy()
        env["GDK_BACKEND"] = "x11"
        script = Path(__file__).with_name("clipboard_x11.py")

        def preexec() -> None:
            # Die if the assistant exits, so restarts don't pile up watchers.
            import ctypes

            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            libc.prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG

        self._watcher = subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            bufsize=1,
            preexec_fn=preexec,
        )
        threading.Thread(target=self._read_watcher, daemon=True).start()

    def _read_watcher(self) -> None:
        proc = self._watcher
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                text = json.loads(line).get("text") or ""
            except json.JSONDecodeError:
                continue
            GLib.idle_add(self._ingest, text)

    def _ingest(self, text: str) -> bool:
        self.capture_on = True
        if self.history.add(text) and self._popup is not None and self._popup.get_visible():
            self._popup.refresh()
        return False

    def show(self) -> None:
        if self._app is None:
            return
        if self._popup is None:
            self._popup = ClipboardWindow(self._app, self)
        self._popup.present_popup()

    def pick(self, text: str) -> None:
        if self._popup is not None:
            self._popup.hide()
        self.history.add(text)
        pasted = request_paste(text)
        if self._popup is not None and not pasted:
            # The text is on the clipboard either way. Say so next time they open it.
            self._popup._status("Copied. Press Ctrl+V.")
