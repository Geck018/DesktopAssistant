#!/usr/bin/env python3
"""
Morning Assistant — todos, system updates, login brief, optional tray icon.

Usage:
  ./quick-todo              # normal window
  ./quick-todo --morning    # login mode: brief once/day, else tray/hidden
  ./quick-todo --brief      # force morning brief view
  ./quick-todo --ping --action=notify|open|both [--slot=HH:MM]
  ./quick-todo --clipboard      # history popup (also Super+V)
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk, Pango

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from modules import state as app_state
from modules import todos as todo_mod
from modules import updates as upd_mod
from modules import config as cfg_mod
from modules import notify as notify_mod
from modules import clipboard as clip_mod
from modules import style as style_mod

TODO_PATH = APP_DIR / "todo.md"
ICON_PATH = APP_DIR / "icon.png"
APP_ID = "morning-assistant"
ICON_FALLBACK = "checkbox-checked-symbolic"
APP_TITLE = "Assistant"
SNI_PATH = "/org/ayatana/NotificationItem/" + "".join(
    ch if ch.isalnum() else "_" for ch in APP_ID
)
SNI_IFACE = "org.kde.StatusNotifierItem"


def try_app_indicator():
    for ns in ("AyatanaAppIndicator3", "AppIndicator3"):
        try:
            gi.require_version(ns, "0.1")
            return getattr(__import__("gi.repository", fromlist=[ns]), ns)
        except (ValueError, ImportError, AttributeError):
            continue
    return None


class AssistantApp(Gtk.Application):
    def __init__(self, morning: bool = False, force_brief: bool = False):
        super().__init__(
            application_id="local.morning.assistant",
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.morning = morning
        self.force_brief = force_brief
        self._open_clipboard = False
        self.clips = clip_mod.Service()
        self.window: Gtk.ApplicationWindow | None = None
        self.stack: Gtk.Stack | None = None
        self.switcher: Gtk.StackSwitcher | None = None

        # Todos
        self.list_box: Gtk.ListBox | None = None
        self.entry: Gtk.Entry | None = None
        self.todo_status: Gtk.Label | None = None
        self.items: list[todo_mod.Item] = []

        # Brief
        self.brief_greeting: Gtk.Label | None = None
        self.brief_todos: Gtk.Box | None = None
        self.brief_todo_count: Gtk.Label | None = None
        self.brief_updates: Gtk.Box | None = None
        self.brief_update_count: Gtk.Label | None = None
        self.brief_meta: Gtk.Label | None = None
        self.update_btn: Gtk.Button | None = None
        self.refresh_btn: Gtk.Button | None = None
        self.report: upd_mod.UpdateReport | None = None

        self.indicator = None
        self._AppIndicator = try_app_indicator()
        self._busy = False
        self._scheduler_id = None
        self._activation_token: str | None = None
        self._bus_filter_id: int | None = None

    # ── lifecycle ──────────────────────────────────────────────
    def do_command_line(self, command_line):
        args = parse_args(command_line.get_arguments()[1:], exit_on_error=False)
        if args is None:
            return 1
        if args.morning:
            self.morning = True
        if args.brief:
            self.force_brief = True
        if args.clipboard:
            self._open_clipboard = True
        self.activate()
        return 0

    def do_activate(self):
        want_clip = self._open_clipboard
        want_brief = self.force_brief
        self._open_clipboard = False
        self.force_brief = False
        if self.window:
            if want_clip:
                self.clips.show()
                return
            self.force_brief = want_brief
            self._maybe_show_on_activate()
            self.force_brief = False
            return

        self.items = todo_mod.load_items(TODO_PATH)
        if ICON_PATH.exists():
            Gtk.Window.set_default_icon_from_file(str(ICON_PATH))

        style_mod.install(cfg_mod.theme_name())
        self.window = Gtk.ApplicationWindow(application=self, title=APP_TITLE)
        self.window.get_style_context().add_class("assistant")
        self.window.set_default_size(500, 660)
        self.window.connect("delete-event", self._on_close)
        if ICON_PATH.exists():
            self.window.set_icon_from_file(str(ICON_PATH))

        header = Gtk.HeaderBar(title=APP_TITLE)
        header.set_show_close_button(True)
        self.window.set_titlebar(header)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.switcher = Gtk.StackSwitcher(stack=self.stack)
        header.set_custom_title(self.switcher)

        clear_btn = Gtk.Button.new_from_icon_name(
            "edit-clear-all-symbolic", Gtk.IconSize.BUTTON
        )
        clear_btn.set_relief(Gtk.ReliefStyle.NONE)
        clear_btn.get_style_context().add_class("icon-quiet")
        clear_btn.set_tooltip_text("Clear completed todos")
        clear_btn.connect("clicked", self._clear_completed)
        header.pack_end(clear_btn)

        brief_btn = Gtk.Button.new_from_icon_name(
            "view-refresh-symbolic", Gtk.IconSize.BUTTON
        )
        brief_btn.set_relief(Gtk.ReliefStyle.NONE)
        brief_btn.get_style_context().add_class("icon-quiet")
        brief_btn.set_tooltip_text("Open morning brief / refresh")
        brief_btn.connect("clicked", self._show_brief_and_refresh)
        header.pack_end(brief_btn)

        header.pack_end(self._theme_button())

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.window.add(root)
        root.pack_start(self.stack, True, True, 0)

        self.stack.add_titled(self._build_brief_page(), "brief", "Brief")
        self.stack.add_titled(self._build_todos_page(), "todos", "Todos")

        self._rebuild_todo_list()
        self._setup_tray()
        self._refresh_todo_status()
        self._paint_brief_todos()
        self._start_scheduler()

        show_brief = want_brief or (
            self.morning and not app_state.brief_already_shown_today()
        )
        # Pick a page before anything is mapped. A stack with no visible
        # child, or a window shown via present() before its children are
        # show()'d, comes up as an empty grey frame.
        self.stack.set_visible_child_name("brief" if show_brief else "todos")
        self._prepare_widgets()
        self.clips.start(self)

        if want_clip:
            self.clips.show()
            if show_brief:
                app_state.mark_brief_shown()
                app_state.log("morning brief shown")
                self._start_update_scan(refresh=False, quiet=False)
            else:
                if self.morning and self.indicator is not None:
                    app_state.log("morning: brief already shown; starting hidden")
                self._start_update_scan(refresh=False, quiet=True)
            return

        if self.morning and not show_brief and self.indicator is not None:
            # Already briefed today — live in tray / stay quiet.
            # Children are already marked visible, so a later present()
            # paints the UI instead of a grey window.
            app_state.log("morning: brief already shown; starting hidden")
            self._start_update_scan(refresh=False, quiet=True)
            return

        self._present_window()
        if show_brief:
            app_state.mark_brief_shown()
            app_state.log("morning brief shown")
            # Use cache first so login isn't blocked by a password prompt.
            # User can hit Refresh for a live apt update.
            self._start_update_scan(refresh=False, quiet=False)
        else:
            self._start_update_scan(refresh=False, quiet=True)

    def _prepare_widgets(self):
        """Mark the widget tree visible without mapping the window itself.

        Gtk.Window.present() only shows the window. Children that were never
        show()'d stay invisible, which is the grey empty frame.
        """
        if self.window is None:
            return
        titlebar = self.window.get_titlebar()
        if titlebar is not None:
            titlebar.show_all()
        child = self.window.get_child()
        if child is not None:
            child.show_all()

    def _present_window(self):
        """Show and raise the window. Safe to call from the tray or a second launch."""
        if self.window is None:
            return False
        self._prepare_widgets()
        token = self._activation_token
        self._activation_token = None
        if token:
            try:
                self.window.set_startup_id(token)
            except Exception as e:
                app_state.log(f"startup id failed: {e}")
        self.window.show_all()
        self.window.present()
        # A tray click often has no Wayland activation token. Mutter then
        # leaves the window unmapped or buried. keep_above forces it forward,
        # then we drop it so it doesn't stay stuck on top.
        if not self.window.is_active():
            self.window.set_keep_above(True)
            GLib.timeout_add(250, self._drop_keep_above)
        GLib.idle_add(self._ensure_painted)
        return False

    def _drop_keep_above(self):
        if self.window is not None:
            self.window.set_keep_above(False)
        return False

    def _ensure_painted(self):
        if self.window is None or not self.window.get_visible():
            return False
        self._prepare_widgets()
        self.window.queue_resize()
        self.window.queue_draw()
        return False

    def _maybe_show_on_activate(self):
        assert self.window is not None
        if self.force_brief and self.stack is not None:
            self.stack.set_visible_child_name("brief")
        self._present_window()
        if self.force_brief:
            self._start_update_scan(refresh=True, quiet=False)

    def _theme_button(self) -> Gtk.Widget:
        button = Gtk.MenuButton()
        button.add(
            Gtk.Image.new_from_icon_name(
                "preferences-system-symbolic", Gtk.IconSize.BUTTON
            )
        )
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.get_style_context().add_class("icon-quiet")
        button.set_tooltip_text("Theme")

        pop = Gtk.Popover.new(button)
        pop.get_style_context().add_class("assistant")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(14)
        box.set_margin_end(16)
        title = Gtk.Label(label="THEME", xalign=0)
        title.get_style_context().add_class("kicker")
        box.pack_start(title, False, False, 0)

        group: Gtk.RadioButton | None = None
        current = style_mod.current()
        for name, label, blurb in style_mod.CHOICES:
            if group is None:
                radio = Gtk.RadioButton.new_with_label(None, label)
            else:
                radio = Gtk.RadioButton.new_with_label_from_widget(group, label)
            group = radio
            radio.set_active(name == current)
            radio.connect("toggled", self._on_theme_toggled, name)
            note = Gtk.Label(label=blurb, xalign=0)
            note.get_style_context().add_class("muted")
            note.set_margin_start(24)
            note.set_margin_bottom(2)
            box.pack_start(radio, False, False, 0)
            box.pack_start(note, False, False, 0)

        box.show_all()
        pop.add(box)
        button.set_popover(pop)
        return button

    def _on_theme_toggled(self, button: Gtk.RadioButton, name: str) -> None:
        if not button.get_active() or style_mod.current() == name:
            return
        style_mod.apply(name)
        cfg_mod.set_theme(name)

    # ── Brief page ─────────────────────────────────────────────
    def _build_brief_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        page.pack_start(scroll, True, True, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(18)
        content.set_margin_bottom(16)
        content.set_margin_start(20)
        content.set_margin_end(20)
        scroll.add(content)

        self.brief_greeting = Gtk.Label(
            label=f"Good {self._daypart()} Marnus", xalign=0
        )
        self.brief_greeting.get_style_context().add_class("hero")
        content.pack_start(self.brief_greeting, False, False, 0)

        date = Gtk.Label(
            label=datetime.now().strftime("%A, %-d %B"), xalign=0
        )
        date.get_style_context().add_class("date")
        date.set_margin_top(2)
        content.pack_start(date, False, False, 0)

        rule = Gtk.Box()
        rule.set_size_request(36, 2)
        rule.set_halign(Gtk.Align.START)
        rule.set_margin_top(4)
        rule.get_style_context().add_class("rule")
        content.pack_start(rule, False, False, 0)

        todo_card, self.brief_todo_count = self._card("Open")
        content.pack_start(todo_card, False, False, 0)
        self.brief_todos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.brief_todos.set_margin_top(12)
        todo_card.pack_start(self.brief_todos, False, False, 0)

        update_card, self.brief_update_count = self._card("Updates")
        content.pack_start(update_card, False, False, 0)
        self.brief_updates = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.brief_updates.set_margin_top(12)
        update_card.pack_start(self.brief_updates, False, False, 0)
        self._set_update_body("Checking…", muted=True)

        self.brief_meta = Gtk.Label(xalign=0)
        self.brief_meta.set_line_wrap(True)
        self.brief_meta.get_style_context().add_class("muted")
        self.brief_meta.set_margin_top(8)
        self.brief_meta.set_no_show_all(True)
        self.brief_meta.hide()
        update_card.pack_start(self.brief_meta, False, False, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.get_style_context().add_class("footer")
        actions.set_margin_top(4)
        actions.set_margin_bottom(14)
        actions.set_margin_start(16)
        actions.set_margin_end(16)
        page.pack_end(actions, False, False, 0)

        self.refresh_btn = Gtk.Button.new_with_label("Refresh")
        self.refresh_btn.get_style_context().add_class("quiet")
        self.refresh_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.refresh_btn.connect("clicked", lambda *_: self._start_update_scan(True, False))
        actions.pack_start(self.refresh_btn, False, False, 0)

        self.update_btn = Gtk.Button.new_with_label("Update now")
        self.update_btn.get_style_context().add_class("suggested-action")
        self.update_btn.set_sensitive(False)
        self.update_btn.connect("clicked", self._on_update_now)
        actions.pack_start(self.update_btn, False, False, 0)

        todos_btn = Gtk.Button.new_with_label("Todos")
        todos_btn.get_style_context().add_class("quiet")
        todos_btn.set_relief(Gtk.ReliefStyle.NONE)
        todos_btn.connect(
            "clicked", lambda *_: self.stack.set_visible_child_name("todos")
        )
        actions.pack_end(todos_btn, False, False, 0)

        dismiss = Gtk.Button.new_with_label("Dismiss")
        dismiss.get_style_context().add_class("quiet")
        dismiss.set_relief(Gtk.ReliefStyle.NONE)
        dismiss.connect("clicked", self._dismiss_brief)
        actions.pack_end(dismiss, False, False, 0)

        return page

    def _card(self, kicker: str) -> tuple[Gtk.Box, Gtk.Label]:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.get_style_context().add_class("card")
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label=kicker.upper(), xalign=0)
        title.get_style_context().add_class("kicker")
        head.pack_start(title, False, False, 0)
        count = Gtk.Label(label="", xalign=0.5)
        count.get_style_context().add_class("count-quiet")
        head.pack_end(count, False, False, 0)
        card.pack_start(head, False, False, 0)
        return card, count

    def _set_pill(self, label: Gtk.Label | None, n: int | None) -> None:
        if label is None:
            return
        ctx = label.get_style_context()
        if n is None:
            label.set_text("")
            ctx.remove_class("count")
            ctx.add_class("count-quiet")
            return
        label.set_text(str(n))
        if n:
            ctx.add_class("count")
            ctx.remove_class("count-quiet")
        else:
            ctx.remove_class("count")
            ctx.add_class("count-quiet")

    def _daypart(self) -> str:
        h = datetime.now().hour
        if h < 12:
            return "Morning"
        if h < 18:
            return "Afternoon"
        return "Evening"

    def _paint_brief_todos(self):
        assert self.brief_todos is not None
        for child in list(self.brief_todos.get_children()):
            self.brief_todos.remove(child)
        open_ = todo_mod.open_items(self.items)
        self._set_pill(self.brief_todo_count, len(open_))
        if not open_:
            empty = Gtk.Label(label="Nothing waiting.", xalign=0)
            empty.get_style_context().add_class("muted")
            self.brief_todos.add(empty)
        else:
            for item in open_[:12]:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                mark = Gtk.Label(label="·", xalign=0)
                mark.get_style_context().add_class("mark")
                mark.set_valign(Gtk.Align.START)
                text = Gtk.Label(label=item.text, xalign=0)
                text.set_line_wrap(True)
                text.set_selectable(True)
                text.set_hexpand(True)
                row.pack_start(mark, False, False, 0)
                row.pack_start(text, True, True, 0)
                self.brief_todos.add(row)
            extra = len(open_) - 12
            if extra > 0:
                more = Gtk.Label(label=f"{extra} more on the list", xalign=0)
                more.get_style_context().add_class("muted")
                self.brief_todos.add(more)
        self.brief_todos.show_all()

    def _set_update_body(
        self, text: str, *, rows: bool = False, muted: bool = False, preface: str = ""
    ) -> None:
        assert self.brief_updates is not None
        for child in list(self.brief_updates.get_children()):
            self.brief_updates.remove(child)
        if preface:
            note = Gtk.Label(label=preface, xalign=0)
            note.set_line_wrap(True)
            note.set_margin_bottom(8)
            note.get_style_context().add_class("muted")
            self.brief_updates.add(note)
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            lines = [text]
        if rows:
            for line in lines:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                mark = Gtk.Label(label="·", xalign=0)
                mark.get_style_context().add_class("mark")
                mark.set_valign(Gtk.Align.START)
                lab = Gtk.Label(label=line, xalign=0)
                lab.set_line_wrap(True)
                lab.set_selectable(True)
                lab.set_hexpand(True)
                row.pack_start(mark, False, False, 0)
                row.pack_start(lab, True, True, 0)
                self.brief_updates.add(row)
        else:
            lab = Gtk.Label(label="\n".join(lines), xalign=0)
            lab.set_line_wrap(True)
            lab.set_selectable(True)
            if muted:
                lab.get_style_context().add_class("muted")
            self.brief_updates.add(lab)
        self.brief_updates.show_all()

    def _paint_brief_updates(self):
        assert self.brief_updates is not None
        if self.report is None:
            self._set_update_body("Checking…", muted=True)
            return
        warnings = list(self.report.warnings)
        self._set_pill(self.brief_update_count, self.report.total)
        if self.report.error and self.report.total == 0 and not warnings:
            self._set_update_body(f"Couldn’t refresh:\n{self.report.error}")
            self.update_btn.set_sensitive(False)
            self.brief_meta.hide()
            return
        if self.report.total == 0 and not self.report.error:
            if warnings:
                self._set_update_body("\n".join(warnings))
                self.update_btn.set_sensitive(True)
            else:
                self._set_update_body("Everything is up to date.", muted=True)
                self.update_btn.set_sensitive(False)
        else:
            shown = list(self.report.lines[:20])
            if self.report.total > 20:
                shown.append(f"…and {self.report.total - 20} more")
            self._set_update_body(
                "\n".join(shown),
                rows=True,
                preface="\n".join(warnings),
            )
            self.update_btn.set_sensitive(True)
        bits = []
        if self.report.error:
            bits.append(f"Note: {self.report.error[:120]}")
        if self.report.warnings:
            bits.append("NVIDIA module missing for a kernel")
        if self.report.reboot_required:
            bits.append("Reboot pending. It will not be forced.")
        if bits:
            self.brief_meta.set_text(" · ".join(bits))
            self.brief_meta.show()
        else:
            self.brief_meta.hide()
        self._refresh_todo_status()

    def _start_update_scan(self, refresh: bool, quiet: bool):
        if self._busy:
            return
        self._busy = True
        if self.refresh_btn:
            self.refresh_btn.set_sensitive(False)
        if self.brief_updates and not quiet:
            self._set_update_body(
                "Refreshing package lists…\nApprove the password prompt if it appears."
                if refresh
                else "Checking cached package lists…",
                muted=True,
            )

        def work():
            try:
                report = upd_mod.gather(refresh=refresh)
            except Exception as e:
                report = upd_mod.UpdateReport([], [], False, str(e))
            GLib.idle_add(self._on_scan_done, report)

        threading.Thread(target=work, daemon=True).start()

    def _on_scan_done(self, report: upd_mod.UpdateReport):
        self._busy = False
        self.report = report
        if self.refresh_btn:
            self.refresh_btn.set_sensitive(True)
        self._paint_brief_updates()
        app_state.log(
            f"scan: {report.total} updates reboot={report.reboot_required} warnings={len(report.warnings)}"
        )
        return False

    def _on_update_now(self, *_args):
        if self._busy:
            return
        self._busy = True
        self.update_btn.set_sensitive(False)
        self.refresh_btn.set_sensitive(False)
        self._set_update_body(
            "Updating…\n"
            "Approve the password prompt if it appears.\n"
            "Kernel and NVIDIA packages are included.\n"
            "No reboot will be forced.",
            muted=True,
        )

        def work():
            ok, msg = upd_mod.apply_updates()
            GLib.idle_add(self._on_update_done, ok, msg)

        threading.Thread(target=work, daemon=True).start()

    def _on_update_done(self, ok: bool, msg: str):
        self._busy = False
        self.refresh_btn.set_sensitive(True)
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            message_type=Gtk.MessageType.INFO if ok else Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Updates" if ok else "Update failed",
            secondary_text=msg,
        )
        dialog.run()
        dialog.destroy()
        app_state.log(("update ok: " if ok else "update failed: ") + " ".join(msg.split())[:300])
        self._start_update_scan(refresh=False, quiet=False)
        return False

    def _dismiss_brief(self, *_args):
        app_state.mark_brief_shown()
        if self.indicator is not None:
            self.window.hide()
        else:
            self.stack.set_visible_child_name("todos")

    def _show_brief_and_refresh(self, *_args):
        self.stack.set_visible_child_name("brief")
        self._paint_brief_todos()
        self._present_window()
        self._start_update_scan(refresh=True, quiet=False)

    # ── Todos page ─────────────────────────────────────────────
    def _build_todos_page(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        page.pack_start(scroll, True, True, 0)

        self.list_box = Gtk.ListBox()
        self.list_box.get_style_context().add_class("todos")
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.add(self.list_box)

        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add_row.get_style_context().add_class("composer")
        add_row.set_margin_top(10)
        add_row.set_margin_bottom(12)
        add_row.set_margin_start(16)
        add_row.set_margin_end(16)
        page.pack_end(add_row, False, False, 0)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Dump a todo…")
        self.entry.set_hexpand(True)
        self.entry.connect("activate", self._add_from_entry)
        add_row.pack_start(self.entry, True, True, 0)

        add_btn = Gtk.Button.new_with_label("Add")
        add_btn.get_style_context().add_class("suggested-action")
        add_btn.connect("clicked", self._add_from_entry)
        add_row.pack_start(add_btn, False, False, 0)

        self.todo_status = Gtk.Label(xalign=0)
        self.todo_status.set_margin_start(18)
        self.todo_status.set_margin_end(12)
        self.todo_status.set_margin_bottom(8)
        self.todo_status.get_style_context().add_class("muted")
        page.pack_end(self.todo_status, False, False, 0)

        return page

    def _find(self, uid: int) -> todo_mod.Item | None:
        for it in self.items:
            if it.uid == uid:
                return it
        return None

    def _rebuild_todo_list(self):
        assert self.list_box is not None
        for child in list(self.list_box.get_children()):
            self.list_box.remove(child)
        for item in self.items:
            self.list_box.add(self._make_row(item))
        self.list_box.show_all()
        self._paint_brief_todos()

    def _make_row(self, item: todo_mod.Item) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_start(12)
        box.set_margin_end(8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        row.add(box)

        check = Gtk.CheckButton()
        check.set_active(item.done)
        check.connect("toggled", self._on_toggle, item.uid)
        box.pack_start(check, False, False, 0)

        label = Gtk.Label(label=item.text, xalign=0)
        label.set_line_wrap(True)
        label.set_hexpand(True)
        self._style_label(label, item.done)
        box.pack_start(label, True, True, 0)

        del_btn = Gtk.Button.new_from_icon_name(
            "user-trash-symbolic", Gtk.IconSize.BUTTON
        )
        del_btn.set_relief(Gtk.ReliefStyle.NONE)
        del_btn.get_style_context().add_class("icon-quiet")
        del_btn.set_tooltip_text("Delete")
        del_btn.connect("clicked", self._on_delete, item.uid)
        box.pack_end(del_btn, False, False, 0)

        row._todo_label = label  # type: ignore[attr-defined]
        return row

    def _style_label(self, label: Gtk.Label, done: bool):
        ctx = label.get_style_context()
        if done:
            ctx.add_class("done")
            attr = Pango.AttrList()
            attr.insert(Pango.attr_strikethrough_new(True))
            label.set_attributes(attr)
        else:
            ctx.remove_class("done")
            label.set_attributes(None)

    def _persist(self):
        todo_mod.save_items(TODO_PATH, self.items)
        self._refresh_todo_status()
        self._paint_brief_todos()

    def _on_toggle(self, button: Gtk.CheckButton, uid: int):
        item = self._find(uid)
        if not item:
            return
        item.done = button.get_active()
        row = button.get_parent().get_parent()
        label = getattr(row, "_todo_label", None)
        if label:
            self._style_label(label, item.done)
        self._persist()

    def _on_delete(self, _button, uid: int):
        self.items = [i for i in self.items if i.uid != uid]
        self._persist()
        self._rebuild_todo_list()

    def _add_from_entry(self, *_args):
        assert self.entry is not None
        text = self.entry.get_text().strip()
        if not text:
            return
        self.items.append(todo_mod.Item(text=text, done=False))
        self.entry.set_text("")
        self._persist()
        self._rebuild_todo_list()
        self.entry.grab_focus()

    def _clear_completed(self, *_args):
        self.items = [i for i in self.items if not i.done]
        self._persist()
        self._rebuild_todo_list()

    def _refresh_todo_status(self):
        open_n = sum(1 for i in self.items if not i.done)
        done_n = sum(1 for i in self.items if i.done)
        upd_n = self.report.total if self.report else 0
        if self.todo_status:
            text = f"{open_n} open · {done_n} done"
            if not self.indicator:
                text += " · tray off"
            self.todo_status.set_text(text)
        if self.window:
            self.window.set_title(
                f"{APP_TITLE} · {open_n} open"
                + (f" · {upd_n} upd" if upd_n else "")
            )
        if self.indicator is not None:
            badge = open_n + upd_n
            try:
                self.indicator.set_label(str(badge) if badge else "", "")
            except Exception:
                pass

    # ── Window / tray ──────────────────────────────────────────
    def _on_close(self, *_args):
        if self.indicator is not None:
            self.window.hide()
            app_state.log("window hidden to tray")
            return True
        return False

    def _hide_window(self, *_args):
        if self.window is not None and self.indicator is not None:
            self.window.hide()
            app_state.log("window hidden to tray")

    def _setup_tray(self):
        if self.indicator is not None or not self._AppIndicator:
            return

        AppIndicator = self._AppIndicator
        menu = Gtk.Menu()

        show_item = Gtk.MenuItem(label="Show")
        show_item.connect("activate", lambda *_: self._present_window())
        menu.append(show_item)

        hide_item = Gtk.MenuItem(label="Hide")
        hide_item.connect("activate", self._hide_window)
        menu.append(hide_item)

        brief_item = Gtk.MenuItem(label="Morning brief")
        brief_item.connect("activate", self._show_brief_and_refresh)
        menu.append(brief_item)

        todos_item = Gtk.MenuItem(label="Todos")
        todos_item.connect("activate", self._tray_show_todos)
        menu.append(todos_item)

        clip_item = Gtk.MenuItem(label="Clipboard")
        clip_item.connect("activate", lambda *_: self.clips.show())
        menu.append(clip_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_: self.quit())
        menu.append(quit_item)
        menu.show_all()

        icon = str(ICON_PATH) if ICON_PATH.exists() else ICON_FALLBACK
        self.indicator = AppIndicator.Indicator.new(
            APP_ID,
            icon,
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(menu)
        self.indicator.set_title(APP_TITLE)
        if ICON_PATH.exists():
            try:
                self.indicator.set_icon_full(str(ICON_PATH), APP_TITLE)
            except Exception:
                pass
        try:
            self.indicator.set_secondary_activate_target(show_item)
        except Exception:
            pass
        self._install_activation_filter()

    def _install_activation_filter(self):
        """Accept the activation token GNOME sends when the tray icon is clicked.

        libayatana-appindicator 0.5.x does not implement ProvideXdgActivationToken.
        The shell then marks that startup as failed, and Mutter drops the window
        we try to raise from the top bar. Reply to the call ourselves and keep
        the token for the next present().
        """
        if self._bus_filter_id is not None:
            return
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as e:
            app_state.log(f"session bus unavailable: {e}")
            return
        self._bus_filter_id = bus.add_filter(self._on_bus_message, None)
        app_state.log(f"tray activation filter on {SNI_PATH}")

    def _on_bus_message(self, connection, message, incoming, _user_data):
        if not incoming:
            return message
        if message.get_message_type() != Gio.DBusMessageType.METHOD_CALL:
            return message
        if message.get_path() != SNI_PATH:
            return message
        if message.get_interface() not in (None, SNI_IFACE):
            return message
        member = message.get_member()
        if member == "ProvideXdgActivationToken":
            token = ""
            body = message.get_body()
            if body is not None:
                unpacked = body.unpack() if hasattr(body, "unpack") else body
                if isinstance(unpacked, tuple) and unpacked:
                    token = str(unpacked[0] or "")
            if token:
                self._activation_token = token
                app_state.log("tray activation token received")
            self._dbus_ack(connection, message)
            return None
        if member == "Activate":
            # Double-click on the top-bar icon. The token, if any, arrived first.
            self._dbus_ack(connection, message)
            GLib.idle_add(self._present_window)
            return None
        return message

    def _dbus_ack(self, connection, message):
        reply = Gio.DBusMessage.new_method_reply(message)
        connection.send_message(reply, Gio.DBusSendMessageFlags.NONE)

    def _tray_show_todos(self, *_args):
        self.stack.set_visible_child_name("todos")
        self._present_window()
        if self.entry:
            self.entry.grab_focus()

    # ── Schedule ───────────────────────────────────────────────
    def _start_scheduler(self):
        if self._scheduler_id is not None:
            return
        # Poll every 20s; fire at most once per HH:MM slot per day
        self._scheduler_id = GLib.timeout_add_seconds(20, self._scheduler_tick)
        app_state.log("scheduler started")

    def _scheduler_tick(self):
        try:
            now = datetime.now()
            hhmm = f"{now.hour:02d}:{now.minute:02d}"
            for slot in cfg_mod.slots():
                if slot.time != hhmm:
                    continue
                if app_state.slot_already_fired(slot.time):
                    continue
                app_state.mark_slot_fired(slot.time)
                app_state.log(f"in-app schedule fire {slot.time} action={slot.action}")
                self._run_slot_action(slot.action)
        except Exception as e:
            app_state.log(f"scheduler error: {e}")
        return True

    def _run_slot_action(self, action: str):
        action = (action or "both").lower()
        if action in ("notify", "both"):
            notify_mod.maybe_notify()
        if action in ("open", "both"):
            self.items = todo_mod.load_items(TODO_PATH)
            self._rebuild_todo_list()
            self.stack.set_visible_child_name("brief")
            self._paint_brief_todos()
            self._present_window()
            self._start_update_scan(refresh=False, quiet=False)


def daemonize() -> None:
    """Detach from terminal so the process survives without a shell window.

    Skipped when already launched via launch-silent.sh / systemd (ASSISTANT_DAEMONIZED=1),
    or when not attached to a TTY.
    """
    import os

    if os.environ.get("ASSISTANT_DAEMONIZED") == "1":
        try:
            signal.signal(signal.SIGHUP, signal.SIG_IGN)
        except Exception:
            pass
        return

    try:
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    except Exception:
        pass

    # Only fork when started from an interactive terminal
    if not sys.stdin.isatty():
        return

    app_state.ensure()
    log_path = Path(os.environ.get("ASSISTANT_LOG") or app_state.LOG_FILE)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if not os.access(log_path, os.W_OK):
            try:
                log_path.unlink(missing_ok=True)
            except Exception:
                log_path = Path(f"/tmp/assistant-{os.getuid()}.log")
    except Exception:
        log_path = Path(f"/tmp/assistant-{os.getuid()}.log")

    try:
        if os.fork() > 0:
            os._exit(0)
        os.setsid()
        if os.fork() > 0:
            os._exit(0)
    except OSError:
        return

    os.environ["ASSISTANT_DAEMONIZED"] = "1"
    os.chdir(str(APP_DIR))
    try:
        with open(os.devnull, "r") as devnull:
            os.dup2(devnull.fileno(), 0)
        with open(log_path, "a", encoding="utf-8") as logf:
            os.dup2(logf.fileno(), 1)
            os.dup2(logf.fileno(), 2)
    except Exception:
        pass


def run_ping(action: str, slot: str | None) -> int:
    """Scheduled / manual ping without requiring a long-lived UI (notify-only)."""
    app_state.ensure()
    action = (action or "both").lower()
    if action not in ("notify", "open", "both"):
        action = "both"
    if slot and not app_state.slot_already_fired(slot):
        app_state.mark_slot_fired(slot)
    app_state.log(f"ping action={action} slot={slot or '-'}")

    if action in ("notify", "both"):
        notify_mod.maybe_notify(force=False)

    if action in ("open", "both"):
        # Hand off to the GUI (reuses running instance via Gtk.Application id)
        app = AssistantApp(morning=False, force_brief=True)
        return app.run(["assistant", "--brief"])

    return 0


def parse_args(argv: list[str], *, exit_on_error: bool = True):
    p = argparse.ArgumentParser(description=APP_TITLE)
    p.add_argument(
        "--morning",
        action="store_true",
        help="Login mode: show brief once per day, else stay quiet in tray",
    )
    p.add_argument(
        "--brief",
        action="store_true",
        help="Force morning brief view",
    )
    p.add_argument(
        "--ping",
        action="store_true",
        help="Scheduled check-in: notify and/or open (see --action)",
    )
    p.add_argument(
        "--action",
        choices=("notify", "open", "both"),
        default="both",
        help="What --ping should do (default: both)",
    )
    p.add_argument(
        "--slot",
        default=None,
        help="HH:MM slot id for dedupe (used by systemd timers)",
    )
    p.add_argument(
        "--daemon",
        action="store_true",
        help="Detach from terminal (implied by --morning)",
    )
    p.add_argument(
        "--fg",
        action="store_true",
        help="Stay attached to the terminal (debug)",
    )
    p.add_argument(
        "--clipboard",
        action="store_true",
        help="Show clipboard history (Super+V)",
    )
    p.exit_on_error = exit_on_error
    try:
        return p.parse_args(argv)
    except (argparse.ArgumentError, SystemExit):
        if exit_on_error:
            raise
        return None


def main(argv: list[str] | None = None):
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    args = parse_args(argv if argv is not None else sys.argv[1:])
    app_state.ensure()
    cfg_mod.load()  # ensure config.json exists

    # Always ignore hangup so closing a terminal doesn't kill a running assistant
    try:
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
    except Exception:
        pass

    if args.ping:
        # notify-only pings stay short-lived; open may show UI
        if args.action in ("open", "both") and not args.fg:
            daemonize()
        return run_ping(args.action, args.slot)

    if (args.morning or args.daemon) and not args.fg:
        daemonize()

    app = AssistantApp(morning=args.morning, force_brief=args.brief)
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
