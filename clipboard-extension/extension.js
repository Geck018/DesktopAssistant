import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'local.morning.clipboard';
const OBJECT_PATH = '/local/morning/clipboard';
const MAX_ITEMS = 80;

const IFACE = `
<node>
  <interface name="local.morning.clipboard">
    <method name="Get">
      <arg type="as" direction="out" name="items"/>
    </method>
    <method name="Paste">
      <arg type="s" direction="in" name="text"/>
    </method>
    <signal name="Pushed">
      <arg type="s" name="text"/>
    </signal>
  </interface>
</node>`;

export default class AssistantClipboardExtension extends Extension {
    enable() {
        this._items = [];
        this._last = null;
        this._pasteToken = 0;
        this._clipboard = St.Clipboard.get_default();
        this._exported = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._exported.export(Gio.DBus.session, OBJECT_PATH);
        this._nameId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.REPLACE,
            null,
            null,
            null
        );

        this._selection = global.display.get_selection();
        this._ownerId = this._selection.connect('owner-changed', (_sel, type) => {
            if (type !== Meta.SelectionType.SELECTION_CLIPBOARD)
                return;
            this._read();
        });
        // owner-changed can beat the new contents. A short poll catches that
        // and any signal-name mismatch without missing copies.
        this._pollId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            this._read();
            return GLib.SOURCE_CONTINUE;
        });
        this._read();
        console.log('Assistant clipboard capture on');
    }

    disable() {
        if (this._pollId) {
            GLib.source_remove(this._pollId);
            this._pollId = 0;
        }
        if (this._ownerId && this._selection) {
            this._selection.disconnect(this._ownerId);
            this._ownerId = 0;
        }
        this._pasteToken += 1;
        if (this._exported) {
            this._exported.unexport();
            this._exported = null;
        }
        if (this._nameId) {
            Gio.bus_unown_name(this._nameId);
            this._nameId = 0;
        }
        this._clipboard = null;
        this._selection = null;
    }

    Get() {
        return this._items;
    }

    Paste(text) {
        if (!text)
            return;
        this._last = text;
        this._clipboard.set_text(St.ClipboardType.CLIPBOARD, text);
        const token = ++this._pasteToken;
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 280, () => {
            if (token === this._pasteToken)
                this._chordCtrlV();
            return GLib.SOURCE_REMOVE;
        });
    }

    _read() {
        if (!this._clipboard)
            return;
        this._clipboard.get_text(St.ClipboardType.CLIPBOARD, (_clip, text) => {
            this._push(text);
        });
    }

    _push(text) {
        if (!text || !text.trim() || text === this._last)
            return;
        if (text.length > 200000)
            text = text.slice(0, 200000);
        this._last = text;
        const existing = this._items.indexOf(text);
        if (existing !== -1)
            this._items.splice(existing, 1);
        this._items.unshift(text);
        if (this._items.length > MAX_ITEMS)
            this._items.length = MAX_ITEMS;
        try {
            this._exported?.emit_signal('Pushed', new GLib.Variant('(s)', [text]));
        } catch (e) {
            console.log(`Assistant clipboard push failed: ${e}`);
        }
    }

    _chordCtrlV() {
        try {
            const seat = Clutter.get_default_backend().get_default_seat();
            const dev = seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
            const now = global.get_current_time();
            const ctrl = Clutter.KEY_Control_L;
            const v = Clutter.KEY_v;
            dev.notify_keyval(now, ctrl, Clutter.KeyState.PRESSED);
            dev.notify_keyval(now, v, Clutter.KeyState.PRESSED);
            dev.notify_keyval(now, v, Clutter.KeyState.RELEASED);
            dev.notify_keyval(now, ctrl, Clutter.KeyState.RELEASED);
        } catch (e) {
            console.log(`Assistant clipboard paste keys failed: ${e}`);
        }
    }
}
