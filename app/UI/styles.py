"""Centralized design tokens for Secure Notes.

Every colour is a ``(light, dark)`` pair so CustomTkinter widgets switch theme
automatically. Plain Tk widgets (menus, text tags) must resolve a token with
:func:`resolve` whenever the appearance mode changes.
"""

import customtkinter as ctk

FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Cascadia Mono"


class Colors:
    # Surfaces
    bg = ("#FFFFFF", "#161618")           # editor / main canvas
    sidebar = ("#F7F7F8", "#1C1C1F")      # navigation panels
    card = ("#FFFFFF", "#202024")         # dialogs, raised surfaces
    input_bg = ("#FFFFFF", "#232327")
    hover = ("#ECECEF", "#26262B")
    active = ("#E6E6EA", "#2A2A30")       # open note when something else is selected
    selected = ("#E3E6FC", "#2C2E4A")     # current tree selection
    border = ("#E4E4E7", "#2C2C32")
    guide = ("#DCDCE0", "#34343A")        # tree indent guides

    # Text
    text = ("#18181B", "#E8E8EB")
    text_sub = ("#71717A", "#8E8E96")
    text_faint = ("#A1A1AA", "#5E5E66")
    on_primary = ("#FFFFFF", "#FFFFFF")

    # Accents
    primary = ("#4F46E5", "#6366F1")
    primary_hover = ("#4338CA", "#5558E3")
    danger = ("#DC2626", "#E5484D")
    danger_hover = ("#B91C1C", "#C93A3F")
    error = ("#DC2626", "#F87171")
    success = ("#15803D", "#4ADE80")
    code = ("#0F766E", "#5EEAD4")
    selection = ("#C7D2FE", "#3B3F7A")    # text selection inside the editor


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


def resolve(color: tuple[str, str]) -> str:
    """Return the hex value of a token for the current appearance mode."""
    return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
