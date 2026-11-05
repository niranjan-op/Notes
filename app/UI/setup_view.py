"""Create a new vault (either SQLCipher-encrypted database or Obsidian-style local folder)."""

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from app.core import config as cf
from .components import PasswordField, field_label, icon_button, primary_button, secondary_button, text_entry
from .styles import Colors, Fonts, Metrics

MIN_PASSWORD_LENGTH = 6
MODE_ENCRYPTED = "Encrypted database"
MODE_FILESYSTEM = "Local folder"


class SetupView(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=Colors.bg, corner_radius=0)
        self.controller = controller
        self._warning_job = None
        self._parent_dir: Path = cf.default_filesystem_root()
        self._build()

    def _build(self) -> None:
        icon_button(self, "arrow_left", lambda: self.controller.show_frame("WelcomeView"), "Back to vaults").place(
            x=16, y=14)

        column = ctk.CTkFrame(self, fg_color="transparent", width=380)
        column.place(relx=0.5, rely=0.47, anchor="center")

        ctk.CTkLabel(column, text="Create a vault", font=Fonts.header, text_color=Colors.text, anchor="w").pack(fill="x")
        ctk.CTkLabel(
            column,
            text="Choose how your vault should be stored on this computer.",
            font=Fonts.body,
            text_color=Colors.text_sub,
            anchor="w",
            justify="left",
            wraplength=380,
        ).pack(fill="x", pady=(4, 16))

        field_label(column, "Vault name").pack(fill="x", pady=(0, 4))
        self.vault_name_entry = text_entry(column, "e.g. Personal", width=380)
        self.vault_name_entry.pack(fill="x")
        self.vault_name_entry.bind("<KeyRelease>", self._update_path_preview)
        self.vault_name_entry.bind("<Return>", lambda _e: self._on_name_return())

        field_label(column, "Storage type").pack(fill="x", pady=(14, 4))
        self.storage_mode = ctk.CTkSegmentedButton(
            column,
            values=[MODE_ENCRYPTED, MODE_FILESYSTEM],
            command=self._on_mode_change,
            height=34,
            corner_radius=Metrics.radius,
            font=Fonts.body,
            fg_color=Colors.sidebar,
            selected_color=Colors.selected,
            selected_hover_color=Colors.active,
            unselected_color=Colors.sidebar,
            unselected_hover_color=Colors.hover,
            text_color=Colors.text,
        )
        self.storage_mode.set(MODE_ENCRYPTED)
        self.storage_mode.pack(fill="x")

        self.mode_hint = ctk.CTkLabel(
            column,
            text="",
            font=Fonts.small,
            text_color=Colors.text_sub,
            anchor="w",
            justify="left",
            wraplength=380,
        )
        self.mode_hint.pack(fill="x", pady=(6, 0))

        self.mode_body = ctk.CTkFrame(column, fg_color="transparent")
        self.mode_body.pack(fill="x")

        # 1. Encrypted DB fields
        self.encrypted_frame = ctk.CTkFrame(self.mode_body, fg_color="transparent")
        blocked = lambda: self.show_warning("For security, type your password.")
        field_label(self.encrypted_frame, "Master password").pack(fill="x", pady=(12, 4))
        self.password = PasswordField(self.encrypted_frame, f"At least {MIN_PASSWORD_LENGTH} characters", blocked)
        self.password.pack(fill="x")

        field_label(self.encrypted_frame, "Confirm password").pack(fill="x", pady=(12, 4))
        self.confirm = PasswordField(self.encrypted_frame, "Repeat password", blocked)
        self.confirm.pack(fill="x")
        self.confirm.entry.bind("<Return>", lambda _event: self.complete_setup())

        # 2. Local folder (Obsidian-style Windows filesystem) fields
        self.filesystem_frame = ctk.CTkFrame(self.mode_body, fg_color="transparent")
        field_label(self.filesystem_frame, "Parent folder").pack(fill="x", pady=(12, 4))
        loc_row = ctk.CTkFrame(self.filesystem_frame, fg_color="transparent")
        loc_row.pack(fill="x")
        self.location_entry = text_entry(loc_row, "")
        self.location_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.location_entry.configure(state="readonly")
        secondary_button(loc_row, "Browse…", self.browse_location, width=88).pack(side="right")

        self.path_preview = ctk.CTkLabel(
            self.filesystem_frame,
            text="",
            font=Fonts.small,
            text_color=Colors.text_faint,
            anchor="w",
            justify="left",
            wraplength=380,
        )
        self.path_preview.pack(fill="x", pady=(6, 0))

        self.warning_label = ctk.CTkLabel(
            column, text="", font=Fonts.small, text_color=Colors.error, height=18, anchor="w"
        )
        self.warning_label.pack(fill="x", pady=(10, 4))

        self.start_btn = primary_button(column, "Create vault", self.complete_setup, height=38)
        self.start_btn.pack(fill="x")

        self._on_mode_change(MODE_ENCRYPTED)

    def _on_name_return(self) -> None:
        if self.storage_mode.get() == MODE_FILESYSTEM:
            self.complete_setup()
        else:
            self.password.focus()

    def _set_location_text(self, path: Path) -> None:
        self._parent_dir = path
        self.location_entry.configure(state="normal")
        self.location_entry.delete(0, "end")
        self.location_entry.insert(0, str(path))
        self.location_entry.configure(state="readonly")
        self._update_path_preview()

    def _update_path_preview(self, _event=None) -> None:
        raw_name = self.vault_name_entry.get().strip() or "<vault-name>"
        target = self._parent_dir / raw_name
        self.path_preview.configure(text=f"Vault folder: {target}")

    def _on_mode_change(self, mode: str) -> None:
        self.warning_label.configure(text="")
        if mode == MODE_FILESYSTEM:
            self.encrypted_frame.pack_forget()
            self.filesystem_frame.pack(fill="x")
            self.mode_hint.configure(
                text="Notes and images are saved directly as Markdown (.md) files and folders in Windows Explorer, just like Obsidian."
            )
            self._update_path_preview()
        else:
            self.filesystem_frame.pack_forget()
            self.encrypted_frame.pack(fill="x")
            self.mode_hint.configure(
                text="All notes, folders and pasted images are sealed inside a SQLCipher-encrypted database (.db) with your master password."
            )

    def browse_location(self) -> None:
        initial = str(self._parent_dir if self._parent_dir.exists() else Path.home())
        chosen = filedialog.askdirectory(
            parent=self.winfo_toplevel(),
            title="Choose parent folder for your vault",
            initialdir=initial,
        )
        if chosen:
            self._set_location_text(Path(chosen))

    def update_view(self, context=None) -> None:
        self.vault_name_entry.delete(0, "end")
        self.password.clear()
        self.confirm.clear()
        self.warning_label.configure(text="")
        self._set_location_text(cf.default_filesystem_root())
        self.storage_mode.set(MODE_ENCRYPTED)
        self._on_mode_change(MODE_ENCRYPTED)
        self.after(50, self.vault_name_entry.focus_set)

    def show_warning(self, message: str) -> None:
        self.warning_label.configure(text=message)
        if self._warning_job:
            self.after_cancel(self._warning_job)
        self._warning_job = self.after(4000, lambda: self.warning_label.configure(text=""))

    def complete_setup(self) -> None:
        name = self.vault_name_entry.get().strip()
        problem = cf.validate_vault_name(name)
        if problem:
            self.show_warning(problem)
            return
        vaults, _ = cf.read_config() if cf.search_config() else ([], "")
        if name.casefold() in {vault.casefold() for vault in vaults}:
            self.show_warning("A vault with this name already exists.")
            return

        mode = self.storage_mode.get()
        if mode == MODE_FILESYSTEM:
            path_problem = cf.validate_filesystem_vault_path(name, parent_dir=self._parent_dir)
            if path_problem:
                self.show_warning(path_problem)
                return
            try:
                cf.create_filesystem_vault(name, parent_dir=self._parent_dir)
            except (FileExistsError, OSError, ValueError) as exc:
                self.show_warning(str(exc) or "The vault folder could not be created.")
                return
            self.password.clear()
            self.confirm.clear()
            self.controller.show_frame("MainView", context={"vault_name": name, "password": ""})
            return

        password = self.password.get()
        if len(password) < MIN_PASSWORD_LENGTH:
            self.show_warning(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
            return
        if password != self.confirm.get():
            self.show_warning("Passwords do not match.")
            return
        if cf.vault_path(name).exists():
            self.show_warning("A vault with this name already exists.")
            return
        try:
            created = cf.create_db(password, name)
        except (OSError, ImportError):
            created = False
        if not created:
            self.show_warning("The vault could not be created.")
            return
        cf.update_config(name, mode="encrypted")
        self.password.clear()
        self.confirm.clear()
        self.controller.show_frame("LoginView", context={"vault_name": name})
