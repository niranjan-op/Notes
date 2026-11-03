"""Create a new encrypted vault."""

import customtkinter as ctk

from app.core import config as cf
from .components import PasswordField, field_label, icon_button, primary_button, text_entry
from .styles import Colors, Fonts

MIN_PASSWORD_LENGTH = 6


class SetupView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=Colors.bg, corner_radius=0)
        self.controller = controller
        self._warning_job = None
        self._build()

    def _build(self) -> None:
        icon_button(self, "arrow_left", lambda: self.controller.show_frame("WelcomeView"), "Back to vaults").place(
            x=16, y=14)

        column = ctk.CTkFrame(self, fg_color="transparent", width=360)
        column.place(relx=0.5, rely=0.45, anchor="center")

        ctk.CTkLabel(column, text="Create a vault", font=Fonts.header, text_color=Colors.text, anchor="w").pack(fill="x")
        ctk.CTkLabel(
            column, text="Notes are encrypted on this device with your master password.",
            font=Fonts.body, text_color=Colors.text_sub, anchor="w", justify="left", wraplength=360,
        ).pack(fill="x", pady=(4, 20))

        field_label(column, "Vault name").pack(fill="x", pady=(0, 4))
        self.vault_name_entry = text_entry(column, "e.g. Personal", width=360)
        self.vault_name_entry.pack(fill="x")

        blocked = lambda: self.show_warning("For security, type your password.")
        field_label(column, "Master password").pack(fill="x", pady=(14, 4))
        self.password = PasswordField(column, f"At least {MIN_PASSWORD_LENGTH} characters", blocked)
        self.password.pack(fill="x")

        field_label(column, "Confirm password").pack(fill="x", pady=(14, 4))
        self.confirm = PasswordField(column, "Repeat password", blocked)
        self.confirm.pack(fill="x")
        self.confirm.entry.bind("<Return>", lambda _event: self.complete_setup())

        self.warning_label = ctk.CTkLabel(column, text="", font=Fonts.small, text_color=Colors.error, height=18,
                                          anchor="w")
        self.warning_label.pack(fill="x", pady=(8, 4))

        self.start_btn = primary_button(column, "Create vault", self.complete_setup, height=38)
        self.start_btn.pack(fill="x")

    def update_view(self, context=None) -> None:
        self.vault_name_entry.delete(0, "end")
        self.password.clear()
        self.confirm.clear()
        self.warning_label.configure(text="")
        self.after(50, self.vault_name_entry.focus_set)

    def show_warning(self, message: str) -> None:
        self.warning_label.configure(text=message)
        if self._warning_job:
            self.after_cancel(self._warning_job)
        self._warning_job = self.after(4000, lambda: self.warning_label.configure(text=""))

    def complete_setup(self) -> None:
        name = self.vault_name_entry.get().strip()
        password = self.password.get()
        problem = cf.validate_vault_name(name)
        if problem:
            self.show_warning(problem)
            return
        if len(password) < MIN_PASSWORD_LENGTH:
            self.show_warning(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
            return
        if password != self.confirm.get():
            self.show_warning("Passwords do not match.")
            return
        vaults, _ = cf.read_config() if cf.search_config() else ([], "")
        if name.casefold() in {vault.casefold() for vault in vaults} or cf.vault_path(name).exists():
            self.show_warning("A vault with this name already exists.")
            return
        try:
            created = cf.create_db(password, name)
        except (OSError, ImportError):
            created = False
        if not created:
            self.show_warning("The vault could not be created.")
            return
        cf.update_config(name)
        self.password.clear()
        self.confirm.clear()
        self.controller.show_frame("LoginView", context={"vault_name": name})
