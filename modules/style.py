"""Shared window styling for the assistant and the clipboard popup.

Themes are inspired looks, not copies of anyone else's card frames or alphabets.
"""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk

APP_DIR = Path(__file__).resolve().parent.parent
_PROVIDER: Gtk.CssProvider | None = None
_CURRENT = "sakura"

THEMES: dict[str, dict[str, str]] = {
    "sakura": {
        "TEXTURE": (APP_DIR / "assets" / "sakura.png").as_uri(),
        "TILE": "520px",
        "INK": "#140e1c",
        "WASH": "#5a2a68",
        "TEXT": "#f8eef6",
        "BRIGHT": "#fff7fc",
        "SOFT": "#e4c4dc",
        "MUTED": "#c9b0d0",
        "DIM": "#9a84a8",
        "QUIET": "#f0d4ea",
        "ACCENT": "#f4a4cc",
        "ACCENTHOVER": "#f8bdd8",
        "ACCENTINK": "#2a1024",
        "CARD": "#241430",
        "FIELD": "#261832",
        "HOVER": "#321c40",
        "SELECTED": "#3d2450",
        "DISABLED": "#3d2450",
        "VENOM": "#f4a4cc",
        "HERO": "Liberation Serif",
        "TRACK": "0px",
        "HEADER": "#5a2a68",
        "ONWASH": "#f8eef6",
        "PILL": "alpha(#f8eef6, 0.16)",
        "EDGE": "alpha(#f8eef6, 0.08)",
        "FADE": "280px",
    },
    "phyrexia": {
        "TEXTURE": (APP_DIR / "assets" / "phyrexia.png").as_uri(),
        "TILE": "640px",
        "INK": "#1a1b1e",
        "WASH": "#c41a34",
        "TEXT": "#f6f1e6",
        "BRIGHT": "#fffaf4",
        "SOFT": "#e4ddd0",
        "MUTED": "#b7b1a6",
        "DIM": "#7a756c",
        "QUIET": "#f3ece2",
        "ACCENT": "#d01234",
        "ACCENTHOVER": "#e42546",
        "ACCENTINK": "#fff6ee",
        "CARD": "#24262a",
        "FIELD": "#2c2e33",
        "HOVER": "#34363c",
        "SELECTED": "#3a3034",
        "DISABLED": "#3a3c42",
        "VENOM": "#e0233c",
        "HERO": "Liberation Serif",
        "TRACK": "0.4px",
        "HEADER": "#c41a34",
        "ONWASH": "#f6f1e6",
        "PILL": "alpha(#f6f1e6, 0.16)",
        "EDGE": "alpha(#f6f1e6, 0.08)",
        "FADE": "280px",
    },
    "emperors": {
        "TEXTURE": (APP_DIR / "assets" / "emperors.png").as_uri(),
        "TILE": "560px",
        "INK": "#070708",
        "WASH": "#1c1218",
        "TEXT": "#f8cfe0",
        "BRIGHT": "#ffe6f2",
        "SOFT": "#e7b3cc",
        "MUTED": "#b992a6",
        "DIM": "#7c6572",
        "QUIET": "#f0c6da",
        "ACCENT": "#e0b45a",
        "ACCENTHOVER": "#f0cc78",
        "ACCENTINK": "#1a1408",
        "CARD": "#101012",
        "FIELD": "#16161a",
        "HOVER": "#221c20",
        "SELECTED": "#2a2418",
        "DISABLED": "#2a2a30",
        "VENOM": "#e0b45a",
        "HERO": "Liberation Serif",
        "TRACK": "0.6px",
        "HEADER": "#f4b8d0",
        "ONWASH": "#1c1016",
        "PILL": "alpha(#140c10, 0.78)",
        "EDGE": "alpha(#e0b45a, 0.75)",
        "FADE": "220px",
    },
}

CHOICES = (
    ("sakura", "Sakura", "Plum evening and blossoms"),
    ("phyrexia", "Phyrexia", "Dark grey, red, and bone script"),
    ("emperors", "Emperor's Children", "Light pink, black lacquer, and gold"),
)

# Tokens are replaced per theme. Longer names are substituted first so
# ACCENT does not eat ACCENTHOVER.
CSS = """
window.assistant {
  background-color: __INK__;
  background-image: url("__TEXTURE__"), linear-gradient(__WASH__, __INK__ __FADE__);
  background-repeat: repeat, no-repeat;
  background-size: __TILE__ __TILE__, auto;
  color: __TEXT__;
}
window.assistant headerbar {
  background-color: __HEADER__;
  background-image: url("__TEXTURE__");
  background-repeat: repeat;
  background-size: __TILE__ __TILE__;
  border: none;
  box-shadow: none;
  color: __ONWASH__;
}
window.assistant headerbar label {
  color: __ONWASH__;
}
window.assistant headerbar button:not(.titlebutton) {
  background-color: transparent;
  background-image: none;
  box-shadow: none;
  border: none;
  border-radius: 999px;
  color: __ONWASH__;
  padding: 6px;
}
window.assistant headerbar button:not(.titlebutton) image,
window.assistant headerbar button:not(.titlebutton):hover image {
  color: __ONWASH__;
  -gtk-icon-shadow: none;
}
window.assistant headerbar button:not(.titlebutton):hover {
  background-color: alpha(__ONWASH__, 0.16);
  color: __ONWASH__;
}
window.assistant headerbar button.titlebutton,
window.assistant headerbar button.titlebutton image,
window.assistant headerbar button.titlebutton:hover,
window.assistant headerbar button.titlebutton:hover image,
window.assistant headerbar button.titlebutton:backdrop,
window.assistant headerbar button.titlebutton:backdrop image {
  color: __ONWASH__;
  -gtk-icon-shadow: none;
  background-image: none;
}
window.assistant headerbar button.titlebutton:hover {
  background-color: alpha(__ONWASH__, 0.16);
}
window.assistant headerbar stackswitcher button {
  min-height: 0;
  padding: 6px 16px;
  margin: 0 2px;
  border-radius: 999px;
  color: __ONWASH__;
  background-color: transparent;
}
window.assistant headerbar stackswitcher button:checked {
  background-color: __PILL__;
  color: __BRIGHT__;
}
window.assistant headerbar stackswitcher button label {
  color: __ONWASH__;
}
window.assistant headerbar stackswitcher button:checked label {
  color: __BRIGHT__;
}
window.assistant headerbar stackswitcher button:hover {
  background-color: alpha(__TEXT__, 0.1);
}
window.assistant box,
window.assistant scrolledwindow,
window.assistant viewport,
window.assistant list {
  background-color: transparent;
  background-image: none;
  border: none;
  color: __TEXT__;
}
window.assistant label {
  color: __TEXT__;
}
window.assistant label.hero {
  font-family: "__HERO__", serif;
  font-size: 34px;
  font-weight: 400;
  letter-spacing: __TRACK__;
  color: __BRIGHT__;
}
window.assistant label.date {
  font-family: "Ubuntu Sans", "Ubuntu", sans-serif;
  font-size: 13px;
  color: __SOFT__;
}
window.assistant box.rule {
  background-color: __VENOM__;
  border-radius: 999px;
}
window.assistant box.card {
  background-color: alpha(__CARD__, 0.88);
  border-radius: 18px;
  border: 1px solid __EDGE__;
  padding: 16px 18px;
}
window.assistant label.kicker {
  font-family: "Ubuntu Sans", "Ubuntu", sans-serif;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.4px;
  color: __SOFT__;
}
window.assistant label.count {
  font-family: "Ubuntu Sans", "Ubuntu", sans-serif;
  font-size: 12px;
  font-weight: 700;
  color: __ACCENTINK__;
  background-color: __ACCENT__;
  border-radius: 999px;
  padding: 1px 8px;
}
window.assistant label.count-quiet {
  font-family: "Ubuntu Sans", "Ubuntu", sans-serif;
  font-size: 12px;
  font-weight: 600;
  color: __SOFT__;
  background-color: transparent;
  padding: 1px 4px;
}
window.assistant label.muted {
  color: __MUTED__;
  font-size: 13px;
}
window.assistant label.mark {
  color: __VENOM__;
  font-size: 18px;
}
window.assistant label.done {
  color: __DIM__;
}
window.assistant check {
  border-radius: 6px;
  border: 1px solid __DIM__;
  background-color: transparent;
  background-image: none;
  color: __VENOM__;
  min-width: 16px;
  min-height: 16px;
}
window.assistant check:checked {
  background-color: __ACCENT__;
  border-color: __ACCENT__;
  color: __ACCENTINK__;
}
window.assistant selection {
  background-color: alpha(__ACCENT__, 0.35);
  color: __BRIGHT__;
}
window.assistant button.quiet {
  background-color: transparent;
  background-image: none;
  box-shadow: none;
  border: none;
  border-radius: 999px;
  color: __QUIET__;
  padding: 8px 12px;
}
window.assistant button.quiet:hover {
  background-color: alpha(__TEXT__, 0.1);
  color: __BRIGHT__;
}
window.assistant button.suggested-action {
  background-color: __ACCENT__;
  background-image: none;
  box-shadow: none;
  border: none;
  border-radius: 999px;
  color: __ACCENTINK__;
  font-weight: 700;
  padding: 8px 18px;
}
window.assistant button.suggested-action:hover {
  background-color: __ACCENTHOVER__;
  color: __ACCENTINK__;
}
window.assistant button.suggested-action:disabled {
  background-color: __DISABLED__;
  color: __DIM__;
}
window.assistant button.icon-quiet {
  background-color: transparent;
  background-image: none;
  box-shadow: none;
  border: none;
  border-radius: 999px;
  color: __MUTED__;
  padding: 4px;
}
window.assistant button.icon-quiet:hover {
  background-color: alpha(__TEXT__, 0.1);
  color: __BRIGHT__;
}
window.assistant entry {
  background-color: __FIELD__;
  background-image: none;
  color: __TEXT__;
  border-radius: 14px;
  border: 1px solid alpha(__TEXT__, 0.12);
  box-shadow: none;
  padding: 8px 12px;
  caret-color: __VENOM__;
}
window.assistant entry:focus {
  border-color: __VENOM__;
}
window.assistant box.footer,
window.assistant box.composer {
  border-top: 1px solid alpha(__TEXT__, 0.1);
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
  background-color: alpha(__CARD__, 0.88);
  border-radius: 14px;
  border: 1px solid __EDGE__;
  margin: 5px 16px;
}
window.assistant list.todos row:hover {
  background-color: __HOVER__;
}
window.assistant list.clips row {
  border-radius: 12px;
  margin: 2px 0;
}
window.assistant list.clips row:hover {
  background-color: alpha(__TEXT__, 0.06);
}
window.assistant list.clips row:selected {
  background-color: __SELECTED__;
}
window.assistant scrollbar {
  background: transparent;
  border: none;
  box-shadow: none;
}
window.assistant scrollbar slider {
  background-color: alpha(__VENOM__, 0.45);
  border-radius: 999px;
  min-width: 6px;
  min-height: 6px;
}
popover.assistant {
  background-color: __CARD__;
  background-image: none;
  color: __TEXT__;
  border: 1px solid alpha(__TEXT__, 0.12);
}
popover.assistant box,
popover.assistant label {
  background-color: transparent;
  background-image: none;
  color: __TEXT__;
}
popover.assistant label.muted {
  color: __MUTED__;
}
popover.assistant radio {
  color: __TEXT__;
}
popover.assistant radio:checked {
  color: __ACCENT__;
}
"""


def current() -> str:
    return _CURRENT


def _css(theme: str) -> bytes:
    spec = THEMES[theme]
    css = CSS
    for key in sorted(spec, key=len, reverse=True):
        css = css.replace(f"__{key}__", spec[key])
    return css.encode()


def apply(theme: str) -> str:
    """Load a theme into the screen-wide provider. Unknown names fall back."""
    global _PROVIDER, _CURRENT
    if theme not in THEMES:
        theme = "sakura"
    if _PROVIDER is None:
        _PROVIDER = Gtk.CssProvider()
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen,
                _PROVIDER,
                Gtk.STYLE_PROVIDER_PRIORITY_USER,
            )
    _PROVIDER.load_from_data(_css(theme))
    _CURRENT = theme
    screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.reset_widgets(screen)
    return theme


def install(theme: str = "sakura") -> None:
    apply(theme)
