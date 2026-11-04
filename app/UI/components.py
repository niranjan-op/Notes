"""Reusable, theme-aware UI building blocks shared by every view."""

from __future__ import annotations

import sys
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from .brand import asset_path, icon_image
from .styles import Colors, Fonts, Metrics, resolve


class Tooltip:
    """A small delayed tooltip for icon-only controls."""

    DELAY_MS = 450

    def __init__(self, widget: tk.Misc, text: str):
        self.widget = widget
        self.text = text
        self._job: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._job = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self) -> None:
        if self._job:
            self.widget.after_cancel(self._job)
            self._job = None

    def _show(self) -> None:
        self._job = None
        if self._tip or not self.widget.winfo_exists():
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        frame = tk.Frame(tip, bg=resolve(Colors.border), padx=1, pady=1)
        frame.pack()
        tk.Label(
            frame, text=self.text, bg=resolve(Colors.card), fg=resolve(Colors.text),
            font=Fonts.small, padx=8, pady=3,
        ).pack()
        tip.update_idletasks()
        x = self.widget.winfo_rootx() + (self.widget.winfo_width() - tip.winfo_width()) // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        x = max(0, min(x, tip.winfo_screenwidth() - tip.winfo_width()))
        tip.geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None


def icon_button(parent, icon: str, command: Callable[[], None], tooltip: str = "",
                size: int = 30, icon_size: int = 17, tone: str = "muted") -> ctk.CTkButton:
    """A borderless square button showing a single line icon."""
    button = ctk.CTkButton(
        parent, text="", image=icon_image(icon, icon_size, tone), width=size, height=size,
        corner_radius=Metrics.radius, fg_color="transparent", hover_color=Colors.hover,
        command=command,
    )
    if tooltip:
        Tooltip(button, tooltip)
    return button


def primary_button(parent, text: str, command: Callable[[], None], **kwargs) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command, height=kwargs.pop("height", Metrics.button_height),
        corner_radius=Metrics.radius, font=Fonts.body_bold, fg_color=Colors.primary,
        hover_color=Colors.primary_hover, text_color=Colors.on_primary,
        text_color_disabled=Colors.text_faint, **kwargs,
    )


def secondary_button(parent, text: str, command: Callable[[], None], **kwargs) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command, height=kwargs.pop("height", Metrics.button_height),
        corner_radius=Metrics.radius, font=Fonts.body, fg_color="transparent", border_width=1,
        border_color=Colors.border, hover_color=Colors.hover, text_color=Colors.text,
        text_color_disabled=Colors.text_faint, **kwargs,
    )


def danger_button(parent, text: str, command: Callable[[], None], **kwargs) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command, height=kwargs.pop("height", Metrics.button_height),
        corner_radius=Metrics.radius, font=Fonts.body_bold, fg_color=Colors.danger,
        hover_color=Colors.danger_hover, text_color=Colors.on_primary,
        text_color_disabled=Colors.text_faint, **kwargs,
    )


def text_entry(parent, placeholder: str = "", **kwargs) -> ctk.CTkEntry:
    return ctk.CTkEntry(
        parent, placeholder_text=placeholder, height=kwargs.pop("height", Metrics.control_height),
        corner_radius=Metrics.radius, border_width=1, border_color=Colors.border,
        fg_color=Colors.input_bg, text_color=Colors.text, placeholder_text_color=Colors.text_faint,
        font=Fonts.body, **kwargs,
    )


def field_label(parent, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=Fonts.label, text_color=Colors.text_sub, anchor="w")


class PasswordField(ctk.CTkFrame):
    """A password entry with a show/hide icon toggle and clipboard protection."""

    def __init__(self, parent, placeholder: str = "Password", on_blocked_paste: Callable[[], None] | None = None):
        super().__init__(parent, fg_color=Colors.input_bg, border_width=1, border_color=Colors.border,
                         corner_radius=Metrics.radius, height=Metrics.control_height + 4)
        self.pack_propagate(False)
        self._visible = False
        self.entry = ctk.CTkEntry(
            self, show="●", border_width=0, fg_color="transparent", text_color=Colors.text,
            placeholder_text=placeholder, placeholder_text_color=Colors.text_faint, font=Fonts.body,
        )
        self.entry.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=2)
        self.toggle = icon_button(self, "eye", self._toggle, "Show password", size=28, icon_size=16)
        self.toggle.pack(side="right", padx=4)
        for sequence in ("<Control-c>", "<Control-x>"):
            self.entry.bind(sequence, lambda _event: "break")
        self.entry.bind("<Control-v>", lambda _event: (on_blocked_paste() if on_blocked_paste else None, "break")[1])
        self.entry.bind("<FocusIn>", lambda _e: self.configure(border_color=Colors.primary), add="+")
        self.entry.bind("<FocusOut>", lambda _e: self.configure(border_color=Colors.border), add="+")

    def _toggle(self) -> None:
        self._visible = not self._visible
        self.entry.configure(show="" if self._visible else "●")
        self.toggle.configure(image=icon_image("eye_off" if self._visible else "eye", 16))

    def get(self) -> str:
        return self.entry.get()

    def clear(self) -> None:
        self.entry.delete(0, "end")
        if self._visible:
            self._toggle()

    def focus(self) -> None:
        self.entry.focus_set()


def set_window_icon(window: tk.Wm) -> None:
    """Apply the Secure Notes icon to a window (title bar and taskbar)."""
    if sys.platform.startswith("win"):
        icon = asset_path("notes.ico")
        if icon.exists():
            try:
                window.iconbitmap(str(icon))
            except tk.TclError:
                pass
    else:
        png = asset_path("notes.png")
        if png.exists():
            try:
                image = tk.PhotoImage(file=str(png))
                window._app_icon_image = image  # prevent GC
                window.iconphoto(True, image)
            except tk.TclError:
                pass


class Dialog(ctk.CTkToplevel):
    """A modal, branded in-app dialog.

    Handles the CustomTkinter Windows quirks that otherwise break dialogs:
    the default CTk icon override and windows left withdrawn after a theme change.
    """

    def __init__(self, owner: tk.Misc, title: str, width: int = 400, modal: bool = True):
        super().__init__(owner, fg_color=Colors.card)
        self.withdraw()
        self._owner = owner.winfo_toplevel()
        self._modal = modal
        self.title(title)
        self.resizable(False, False)
        self.transient(self._owner)
        self.body = ctk.CTkFrame(self, fg_color="transparent", width=width)
        self.body.pack(fill="both", expand=True, padx=24, pady=(20, 20))
        ctk.CTkFrame(self.body, width=width, height=1, fg_color="transparent").pack(side="bottom")
        self.bind("<Escape>", lambda _event: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        # CTkToplevel resets its icon ~200 ms after creation; apply ours afterwards.
        self.after(260, lambda: set_window_icon(self) if self.winfo_exists() else None)

    def heading(self, text: str, subtitle: str = "") -> None:
        ctk.CTkLabel(self.body, text=text, font=Fonts.header, text_color=Colors.text, anchor="w").pack(fill="x")
        if subtitle:
            ctk.CTkLabel(self.body, text=subtitle, font=Fonts.body, text_color=Colors.text_sub, anchor="w",
                         justify="left", wraplength=360).pack(fill="x", pady=(4, 0))

    def actions(self) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(20, 0))
        return row

    def present(self) -> None:
        """Center over the owner window, show, and grab input when modal."""
        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        owner = self._owner
        x = owner.winfo_rootx() + (owner.winfo_width() - width) // 2
        y = owner.winfo_rooty() + (owner.winfo_height() - height) // 3
        x = max(0, min(x, self.winfo_screenwidth() - width))
        y = max(0, min(y, self.winfo_screenheight() - height))
        self.geometry(f"+{x}+{y}")
        self.reveal()
        if self._modal:
            self.after(10, self._grab)

    def _grab(self) -> None:
        if not self.winfo_exists():
            return
        try:
            self.grab_set()
        except tk.TclError:
            self.after(30, self._grab)

    def reveal(self) -> None:
        if not self.winfo_exists():
            return
        self.deiconify()
        self.lift()
        self.focus_force()

    def _set_appearance_mode(self, mode_string):  # CustomTkinter hook
        super()._set_appearance_mode(mode_string)
        # The Windows title-bar recolour withdraws the window; make sure it returns.
        self.after(40, self._restore_after_theme_change)

    def _restore_after_theme_change(self) -> None:
        self.reveal()
        if self._modal and self.winfo_exists():
            self._grab()

    def close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


def confirm(owner: tk.Misc, title: str, message: str, confirm_text: str, on_confirm: Callable[[], None],
            danger: bool = True, require_text: str | None = None) -> Dialog:
    """Show a confirmation dialog; optionally require typing ``require_text`` first."""
    dialog = Dialog(owner, title)
    dialog.heading(title, message)
    entry = None
    if require_text is not None:
        field_label(dialog.body, f"Type “{require_text}” to confirm").pack(fill="x", pady=(16, 4))
        entry = text_entry(dialog.body, require_text)
        entry.pack(fill="x")

    def accept() -> None:
        if entry is not None and entry.get().strip() != require_text:
            return
        dialog.close()
        on_confirm()

    row = dialog.actions()
    make = danger_button if danger else primary_button
    accept_button = make(row, confirm_text, accept, width=96)
    accept_button.pack(side="right")
    secondary_button(row, "Cancel", dialog.close, width=86).pack(side="right", padx=(0, 8))
    if entry is not None:
        accept_button.configure(state="disabled")
        entry.bind("<KeyRelease>", lambda _e: accept_button.configure(
            state="normal" if entry.get().strip() == require_text else "disabled"))
        entry.bind("<Return>", lambda _e: accept())
    dialog.bind("<Return>", lambda _e: accept() if entry is None else None)
    dialog.present()
    if entry is not None:
        dialog.after(60, entry.focus_set)
    return dialog
