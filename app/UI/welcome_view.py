"""Vault picker: open, create or delete local vaults."""

import customtkinter as ctk

import app.core.config as cf
from .brand import APP_NAME, APP_VERSION, icon_image, logo_image
from .components import Tooltip, confirm, icon_button, primary_button
from .styles import Colors, Fonts, Metrics


class WelcomeView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=Colors.bg, corner_radius=0)
        self.controller = controller
        self._build()

    def _build(self) -> None:
        theme = icon_button(self, "theme", self._toggle_theme, "Toggle light / dark")
        theme.place(relx=1, x=-16, y=14, anchor="ne")

        column = ctk.CTkFrame(self, fg_color="transparent", width=380)
        column.place(relx=0.5, rely=0.45, anchor="center")

        self.logo = logo_image(52)
        ctk.CTkLabel(column, text="", image=self.logo).pack(pady=(0, 14))
        ctk.CTkLabel(column, text=APP_NAME, font=Fonts.display, text_color=Colors.text).pack()
        ctk.CTkLabel(
            column, text="Encrypted, local-first notes.", font=Fonts.body, text_color=Colors.text_sub,
        ).pack(pady=(4, 26))

        header = ctk.CTkFrame(column, fg_color="transparent")
        header.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(header, text="VAULTS", font=Fonts.section, text_color=Colors.text_faint).pack(side="left")

        self.vault_list = ctk.CTkFrame(
            column, fg_color=Colors.sidebar, border_width=1, border_color=Colors.border,
            corner_radius=Metrics.radius_lg, width=380,
        )
        self.vault_list.pack(fill="x")

        primary_button(column, "Create new vault", lambda: self.controller.show_frame("SetupView"),
                       width=380, height=38).pack(fill="x", pady=(16, 0))

        self.status = ctk.CTkLabel(column, text="", font=Fonts.small, text_color=Colors.error, wraplength=360)
        self.status.pack(pady=(10, 0))

        ctk.CTkLabel(self, text=f"v{APP_VERSION}", font=Fonts.small, text_color=Colors.text_faint).place(
            relx=0.5, rely=1, y=-14, anchor="s")

    def update_view(self, context=None) -> None:
        self.status.configure(text="")
        self.refresh_vault_list()

    def refresh_vault_list(self) -> None:
        for widget in self.vault_list.winfo_children():
            widget.destroy()
        vaults, last_open = cf.read_config() if cf.search_config() else ([], "")
        if not vaults:
            ctk.CTkLabel(
                self.vault_list, text="No vaults yet. Create one to get started.",
                font=Fonts.body, text_color=Colors.text_sub,
            ).pack(padx=16, pady=18)
            return
        ordered = sorted(vaults, key=lambda name: (name != last_open, name.casefold()))
        for index, name in enumerate(ordered):
            if index:
                ctk.CTkFrame(self.vault_list, height=1, fg_color=Colors.border).pack(fill="x", padx=12)
            self._vault_row(name, name == last_open)

    def _vault_row(self, name: str, is_last: bool) -> None:
        row = ctk.CTkFrame(self.vault_list, fg_color="transparent", corner_radius=Metrics.radius, height=46)
        row.pack(fill="x", padx=4, pady=3)
        row.pack_propagate(False)
        icon = ctk.CTkLabel(row, text="", image=icon_image("lock", 17), width=28)
        icon.pack(side="left", padx=(10, 6))
        label = ctk.CTkLabel(row, text=name, font=Fonts.body_bold, text_color=Colors.text, anchor="w")
        label.pack(side="left")
        if is_last:
            ctk.CTkLabel(row, text="Last opened", font=Fonts.small, text_color=Colors.text_faint).pack(
                side="left", padx=(10, 0))
        delete = icon_button(row, "trash", lambda: self._confirm_delete(name), "Delete vault", size=30, icon_size=16)
        delete.pack(side="right", padx=8)
        delete.pack_forget()

        def enter(_event=None):
            row.configure(fg_color=Colors.hover)
            delete.pack(side="right", padx=8)

        def leave(_event=None):
            pointer = row.winfo_containing(*row.winfo_pointerxy())
            if pointer is None or not str(pointer).startswith(str(row)):
                row.configure(fg_color="transparent")
                delete.pack_forget()

        open_vault = lambda _event=None: self.controller.show_frame("LoginView", context={"vault_name": name})
        for widget in (row, icon, label):
            widget.bind("<Enter>", enter)
            widget.bind("<Leave>", leave)
            widget.bind("<Button-1>", open_vault)
            widget.configure(cursor="hand2")
        delete.bind("<Leave>", leave, add="+")
        Tooltip(label, "Open vault")

    def _confirm_delete(self, name: str) -> None:
        confirm(
            self,
            "Delete vault",
            f"This permanently erases “{name}” and every note inside it. "
            "Encrypted data cannot be recovered.",
            "Delete vault",
            lambda: self._delete(name),
            require_text=name,
        )

    def _delete(self, name: str) -> None:
        try:
            cf.delete_vault(name)
        except ValueError:
            self.status.configure(text="That vault name is invalid and was not deleted.")
            return
        except OSError:
            self.status.configure(text="The vault files are in use and could not be deleted. Close other "
                                       "copies of Secure Notes and try again.")
            return
        self.status.configure(text="")
        self.refresh_vault_list()

    def _toggle_theme(self) -> None:
        mode = "light" if ctk.get_appearance_mode() == "Dark" else "dark"
        ctk.set_appearance_mode(mode)
        cf.set_preference("theme", mode)
