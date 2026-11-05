"""Unlock an existing vault with its master password."""

import customtkinter as ctk

from app.core import config as cf
from .brand import logo_image
from .components import PasswordField, icon_button, primary_button
from .styles import Colors, Fonts


class LoginView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=Colors.bg, corner_radius=0)
        self.controller = controller
        self.vault_name = None
        self._warning_job = None
        self._build()

    def _build(self) -> None:
        icon_button(self, "arrow_left", lambda: self.controller.show_frame("WelcomeView"), "Back to vaults").place(
            x=16, y=14)

        column = ctk.CTkFrame(self, fg_color="transparent", width=340)
        column.place(relx=0.5, rely=0.45, anchor="center")

        self.logo = logo_image(44)
        ctk.CTkLabel(column, text="", image=self.logo).pack(pady=(0, 14))
        self.header_label = ctk.CTkLabel(column, text="Unlock vault", font=Fonts.header, text_color=Colors.text)
        self.header_label.pack()
        ctk.CTkLabel(column, text="Enter your master password.", font=Fonts.body, text_color=Colors.text_sub).pack(
            pady=(4, 22))

        self.password = PasswordField(column, "Master password",
                                      on_blocked_paste=lambda: self.show_warning("For security, type your password."))
        self.password.configure(width=340)
        self.password.pack(fill="x")
        self.password.entry.bind("<Return>", lambda _event: self.perform_login())

        self.warning_label = ctk.CTkLabel(column, text="", font=Fonts.small, text_color=Colors.error, height=18)
        self.warning_label.pack(fill="x", pady=(6, 4))

        self.login_btn = primary_button(column, "Unlock", self.perform_login, width=340, height=38)
        self.login_btn.pack(fill="x")

        ctk.CTkLabel(
            column, text="Passwords can't be recovered. Without it, the vault stays sealed.",
            font=Fonts.small, text_color=Colors.text_faint, wraplength=320,
        ).pack(pady=(14, 0))

    def update_view(self, context=None) -> None:
        self.vault_name = (context or {}).get("vault_name")
        if self.vault_name and cf.is_filesystem_vault(self.vault_name):
            self.controller.show_frame("MainView", context={"vault_name": self.vault_name, "password": ""})
            return
        self.header_label.configure(text=f"Unlock {self.vault_name}" if self.vault_name else "Unlock vault")
        self.warning_label.configure(text="")
        self.password.clear()
        self.after(50, self.password.focus)

    def show_warning(self, message: str) -> None:
        self.warning_label.configure(text=message)
        if self._warning_job:
            self.after_cancel(self._warning_job)
        self._warning_job = self.after(3500, lambda: self.warning_label.configure(text=""))

    def perform_login(self) -> None:
        password = self.password.get()
        if not password:
            self.show_warning("Enter your password.")
            return
        if not self.vault_name:
            self.show_warning("No vault selected.")
            return
        if cf.load_config(password, self.vault_name):
            self.password.clear()
            self.controller.show_frame("MainView", context={"vault_name": self.vault_name, "password": password})
        else:
            self.show_warning("Incorrect password.")
            self.password.clear()
            self.password.focus()
