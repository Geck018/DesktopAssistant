"""Shared window styling for the assistant and the clipboard popup."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

_INSTALLED = False

# Plum ink with a pink wash at the top. Scoped to windows that carry the
# "assistant" style class so system dialogs stay on the desktop theme.
CSS = """
window.assistant {
  background-color: #140e1c;
  background-image: linear-gradient(#5a2a68, #140e1c 260px);
  color: #f8eef6;
}
window.assistant headerbar {
  background-color: #5a2a68;
  background-image: none;
  border: none;
  box-shadow: none;
  color: #f8eef6;
}
window.assistant headerbar label {
  color: #f8eef6;
}
window.assistant headerbar button:not(.titlebutton) {
  background-color: transparent;
  background-image: none;
  box-shadow: none;
  border: none;
  border-radius: 999px;
  color: #f0d4ea;
  padding: 6px;
}
window.assistant headerbar button:not(.titlebutton):hover {
  background-color: alpha(#f8eef6, 0.12);
  color: #fff7fc;
}
window.assistant headerbar stackswitcher button {
  min-height: 0;
  padding: 6px 16px;
  margin: 0 2px;
  border-radius: 999px;
  color: #e4c4dc;
  background-color: transparent;
}
window.assistant headerbar stackswitcher button:checked {
  background-color: alpha(#f8eef6, 0.16);
  color: #fff7fc;
}
window.assistant headerbar stackswitcher button:hover {
  background-color: alpha(#f8eef6, 0.1);
}
window.assistant box,
window.assistant scrolledwindow,
window.assistant viewport,
window.assistant list {
  background-color: transparent;
  background-image: none;
  border: none;
  color: #f8eef6;
}
window.assistant label {
  color: #f8eef6;
}
window.assistant label.hero {
  font-family: "Liberation Serif", serif;
  font-size: 34px;
  font-weight: 400;
  color: #fff7fc;
}
window.assistant label.date {
  font-family: "Ubuntu Sans", "Ubuntu", sans-serif;
  font-size: 13px;
  color: #e4c4dc;
}
window.assistant box.rule {
  background-color: #f4a4cc;
  border-radius: 999px;
}
window.assistant box.card {
  background-color: alpha(#241430, 0.92);
  border-radius: 18px;
  border: 1px solid alpha(#f8eef6, 0.08);
  padding: 16px 18px;
}
window.assistant label.kicker {
  font-family: "Ubuntu Sans", "Ubuntu", sans-serif;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.4px;
  color: #e4c4dc;
}
window.assistant label.count {
  font-family: "Ubuntu Sans", "Ubuntu", sans-serif;
  font-size: 12px;
  font-weight: 700;
  color: #2a1024;
  background-color: #f4a4cc;
  border-radius: 999px;
  padding: 1px 8px;
}
window.assistant label.count-quiet {
  font-family: "Ubuntu Sans", "Ubuntu", sans-serif;
  font-size: 12px;
  font-weight: 600;
  color: #e4c4dc;
  background-color: transparent;
  padding: 1px 4px;
}
window.assistant label.muted {
  color: #c9b0d0;
  font-size: 13px;
}
window.assistant label.mark {
  color: #f4a4cc;
  font-size: 18px;
}
window.assistant label.done {
  color: #9a84a8;
}
window.assistant check {
  border-radius: 6px;
  border: 1px solid #9a84a8;
  background-color: transparent;
  background-image: none;
  color: #f4a4cc;
  min-width: 16px;
  min-height: 16px;
}
window.assistant check:checked {
  background-color: #f4a4cc;
  border-color: #f4a4cc;
  color: #2a1024;
}
window.assistant selection {
  background-color: alpha(#f4a4cc, 0.35);
  color: #fff7fc;
}
window.assistant button.quiet {
  background-color: transparent;
  background-image: none;
  box-shadow: none;
  border: none;
  border-radius: 999px;
  color: #f0d4ea;
  padding: 8px 12px;
}
window.assistant button.quiet:hover {
  background-color: alpha(#f8eef6, 0.1);
  color: #fff7fc;
}
window.assistant button.suggested-action {
  background-color: #f4a4cc;
  background-image: none;
  box-shadow: none;
  border: none;
  border-radius: 999px;
  color: #2a1024;
  font-weight: 700;
  padding: 8px 18px;
}
window.assistant button.suggested-action:hover {
  background-color: #f8bdd8;
  color: #2a1024;
}
window.assistant button.suggested-action:disabled {
  background-color: #3d2450;
  color: #9a84a8;
}
window.assistant button.icon-quiet {
  background-color: transparent;
  background-image: none;
  box-shadow: none;
  border: none;
  border-radius: 999px;
  color: #c9b0d0;
  padding: 4px;
}
window.assistant button.icon-quiet:hover {
  background-color: alpha(#f8eef6, 0.1);
  color: #fff7fc;
}
window.assistant entry {
  background-color: #261832;
  background-image: none;
  color: #f8eef6;
  border-radius: 14px;
  border: 1px solid alpha(#f8eef6, 0.12);
  box-shadow: none;
  padding: 8px 12px;
  caret-color: #f4a4cc;
}
window.assistant entry:focus {
  border-color: #f4a4cc;
}
window.assistant box.footer,
window.assistant box.composer {
  border-top: 1px solid alpha(#f8eef6, 0.1);
}
window.assistant list row {
  background-color: transparent;
  background-image: none;
  border: none;
  box-shadow: none;
}
window.assistant list.todos {
  padding-top: 8px;
  padding-bottom: 8px;
}
window.assistant list.todos row {
  background-color: alpha(#241430, 0.92);
  border-radius: 14px;
  border: 1px solid alpha(#f8eef6, 0.08);
  margin: 5px 16px;
}
window.assistant list.todos row:hover {
  background-color: #321c40;
}
window.assistant list.clips row {
  border-radius: 12px;
  margin: 2px 0;
}
window.assistant list.clips row:hover {
  background-color: alpha(#f8eef6, 0.06);
}
window.assistant list.clips row:selected {
  background-color: #3d2450;
}
window.assistant scrollbar {
  background: transparent;
  border: none;
  box-shadow: none;
}
window.assistant scrollbar slider {
  background-color: alpha(#f4a4cc, 0.45);
  border-radius: 999px;
  min-width: 6px;
  min-height: 6px;
}
"""


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode())
    screen = Gdk.Screen.get_default()
    if screen is None:
        return
    Gtk.StyleContext.add_provider_for_screen(
        screen,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_USER,
    )
    _INSTALLED = True
