"""Centralized design tokens and colour-theme palettes for Secure Notes.

Every token on :class:`Colors` is a 2-element ``[light, dark]`` list so
CustomTkinter widgets switch between Light and Dark appearance modes
automatically. Selecting between the built-in ``Default`` theme and the
``Monochrome`` (black & white) theme mutates those ``[light, dark]`` pairs
in-place and repaints all widgets without disturbing the Light / Dark toggle.
"""

from __future__ import annotations

from typing import Callable, Sequence

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode import AppearanceModeTracker

from .brand import sync_brand_palette

FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Cascadia Mono"

COLOR_THEMES = ("default", "monochrome")
COLOR_THEME_LABELS = ("Default", "Monochrome")

_DEFAULT_PALETTE: dict[str, tuple[str, str]] = {
    # Surfaces
    "bg": ("#FFFFFF", "#161618"),
    "sidebar": ("#F7F7F8", "#1C1C1F"),
    "card": ("#FFFFFF", "#202024"),
    "input_bg": ("#FFFFFF", "#232327"),
    "hover": ("#ECECEF", "#26262B"),
    "active": ("#E6E6EA", "#2A2A30"),
    "selected": ("#E3E6FC", "#2C2E4A"),
    "border": ("#E4E4E7", "#2C2C32"),
    "guide": ("#DCDCE0", "#34343A"),

    # Text
    "text": ("#18181B", "#E8E8EB"),
    "text_sub": ("#71717A", "#8E8E96"),
    "text_faint": ("#A1A1AA", "#5E5E66"),
    "on_primary": ("#FFFFFF", "#FFFFFF"),

    # Accents
    "primary": ("#4F46E5", "#6366F1"),
    "primary_hover": ("#4338CA", "#5558E3"),
    "danger": ("#DC2626", "#E5484D"),
    "danger_hover": ("#B91C1C", "#C93A3F"),
    "error": ("#DC2626", "#F87171"),
    "success": ("#15803D", "#4ADE80"),
    "code": ("#0F766E", "#5EEAD4"),
    "code_bg": ("#F3F4F6", "#1E1E24"),
    "highlight": ("#FEF08A", "#6B5A12"),
    "quote_bg": ("#F8F8FA", "#1B1B20"),
    "table_header_bg": ("#F1F2F6", "#23232A"),
    "table_row_bg": ("#FAFAFB", "#1A1A20"),
    "selection": ("#C7D2FE", "#3B3F7A"),
}

_MONO_PALETTE: dict[str, tuple[str, str]] = {
    # Surfaces
    "bg": ("#FFFFFF", "#000000"),
    "sidebar": ("#FAFAFA", "#080808"),
    "card": ("#FFFFFF", "#0C0C0C"),
    "input_bg": ("#FFFFFF", "#0C0C0C"),
    "hover": ("#F0F0F0", "#171717"),
    "active": ("#E6E6E6", "#1F1F1F"),
    "selected": ("#DCDCDC", "#292929"),
    "border": ("#E0E0E0", "#242424"),
    "guide": ("#D6D6D6", "#262626"),

    # Text
    "text": ("#000000", "#FFFFFF"),
    "text_sub": ("#525252", "#A3A3A3"),
    "text_faint": ("#8A8A8A", "#666666"),
    "on_primary": ("#FFFFFF", "#000000"),

    # Accents (strictly monochrome)
    "primary": ("#000000", "#FFFFFF"),
    "primary_hover": ("#262626", "#D9D9D9"),
    "danger": ("#000000", "#FFFFFF"),
    "danger_hover": ("#262626", "#D9D9D9"),
    "error": ("#000000", "#FFFFFF"),
    "success": ("#262626", "#D4D4D4"),
    "code": ("#171717", "#F0F0F0"),
    "code_bg": ("#F2F2F2", "#121212"),
    "highlight": ("#E0E0E0", "#333333"),
    "quote_bg": ("#F7F7F7", "#0D0D0D"),
    "table_header_bg": ("#EFEFEF", "#141414"),
    "table_row_bg": ("#F9F9F9", "#0A0A0A"),
    "selection": ("#D4D4D4", "#383838"),
}


class Colors:
    # Surfaces
    bg = ["#FFFFFF", "#161618"]           # editor / main canvas
    sidebar = ["#F7F7F8", "#1C1C1F"]      # navigation panels
    card = ["#FFFFFF", "#202024"]         # dialogs, raised surfaces
    input_bg = ["#FFFFFF", "#232327"]
    hover = ["#ECECEF", "#26262B"]
    active = ["#E6E6EA", "#2A2A30"]       # open note when something else is selected
    selected = ["#E3E6FC", "#2C2E4A"]     # current tree selection
    border = ["#E4E4E7", "#2C2C32"]
    guide = ["#DCDCE0", "#34343A"]        # tree indent guides

    # Text
    text = ["#18181B", "#E8E8EB"]
    text_sub = ["#71717A", "#8E8E96"]
    text_faint = ["#A1A1AA", "#5E5E66"]
    on_primary = ["#FFFFFF", "#FFFFFF"]

    # Accents
    primary = ["#4F46E5", "#6366F1"]
    primary_hover = ["#4338CA", "#5558E3"]
    danger = ["#DC2626", "#E5484D"]
    danger_hover = ["#B91C1C", "#C93A3F"]
    error = ["#DC2626", "#F87171"]
    success = ["#15803D", "#4ADE80"]
    code = ["#0F766E", "#5EEAD4"]
    code_bg = ["#F3F4F6", "#1E1E24"]
    highlight = ["#FEF08A", "#6B5A12"]
    quote_bg = ["#F8F8FA", "#1B1B20"]
    table_header_bg = ["#F1F2F6", "#23232A"]
    table_row_bg = ["#FAFAFB", "#1A1A20"]
    selection = ["#C7D2FE", "#3B3F7A"]    # text selection inside the editor


class Fonts:
    display = (FONT_FAMILY, 24, "bold")
    header = (FONT_FAMILY, 20, "bold")
    title = (FONT_FAMILY, 26, "bold")
    sub_header = (FONT_FAMILY, 13)
    body = (FONT_FAMILY, 13)
    body_bold = (FONT_FAMILY, 13, "bold")
    small = (FONT_FAMILY, 11)
    small_bold = (FONT_FAMILY, 11, "bold")
    label = (FONT_FAMILY, 12)
    section = (FONT_FAMILY, 11, "bold")
    editor = (FONT_FAMILY, 15)
    icon = (FONT_FAMILY, 15)


class Metrics:
    radius = 6
    radius_lg = 10
    control_height = 34
    button_height = 34
    row_height = 28
    indent = 14
    sidebar_width = 264
    context_width = 248


_active_color_theme = "default"
_palette_listeners: list[Callable[[str], None]] = []


def normalize_color_theme(name: str) -> str:
    """Normalize a colour theme identifier to ``default`` or ``monochrome``."""
    value = (name or "default").strip().lower()
    if value in {"mono", "monochrome", "b&w", "bw", "black & white"}:
        return "monochrome"
    return "default"


def current_color_theme() -> str:
    """Return the active colour theme (``default`` or ``monochrome``)."""
    return _active_color_theme


def color_theme_label(name: str | None = None) -> str:
    """Return the UI label (``Default`` or ``Monochrome``) for a colour theme."""
    return "Monochrome" if normalize_color_theme(name or _active_color_theme) == "monochrome" else "Default"


def on_color_theme_change(listener: Callable[[str], None]) -> None:
    """Register a callback invoked whenever the colour theme changes."""
    if listener not in _palette_listeners:
        _palette_listeners.append(listener)


def _refresh_ctk_widgets() -> None:
    """Repaint all tracked CustomTkinter widgets in the current Light/Dark mode."""
    windows: list[tuple[object, object]] = []
    for callback in list(AppearanceModeTracker.callback_list):
        owner = getattr(callback, "__self__", None)
        if owner is not None and hasattr(owner, "_deactivate_windows_window_header_manipulation"):
            windows.append((owner, owner._deactivate_windows_window_header_manipulation))
            owner._deactivate_windows_window_header_manipulation = True
    try:
        AppearanceModeTracker.update_callbacks()
    finally:
        for owner, prev in windows:
            owner._deactivate_windows_window_header_manipulation = prev


def apply_color_theme(name: str) -> str:
    """Switch the entire app between ``default`` and ``monochrome`` palettes."""
    global _active_color_theme
    normalized = normalize_color_theme(name)
    is_mono = normalized == "monochrome"
    _active_color_theme = normalized

    palette = _MONO_PALETTE if is_mono else _DEFAULT_PALETTE
    for token_name, (light, dark) in palette.items():
        token = getattr(Colors, token_name)
        token[0] = light
        token[1] = dark

    sync_brand_palette(is_mono)
    _refresh_ctk_widgets()

    for listener in list(_palette_listeners):
        try:
            listener(normalized)
        except Exception:
            pass
    return normalized


def resolve(color: Sequence[str]) -> str:
    """Return the hex value of a token for the current appearance mode."""
    return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
