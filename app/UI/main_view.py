"""The unlocked, local-first Markdown workspace."""

from __future__ import annotations

import ctypes
import gc
import re
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

import app.core.config as cf
from app.core.updater import ReleaseInfo, check_for_update, download_installer, launch_windows_installer
from app.core.vault import DuplicateNameError, Note, Vault, safe_filename
from .brand import APP_VERSION, icon_image, logo_image
from .components import (
    Dialog, confirm, field_label, icon_button, primary_button, secondary_button, text_entry,
)
from .markdown_editor import MarkdownEditorController
from .styles import (
    COLOR_THEME_LABELS,
    Colors,
    Fonts,
    Metrics,
    apply_color_theme,
    color_theme_label,
    current_color_theme,
    resolve,
)

EDITOR_FONTS = ("Segoe UI", "Cascadia Mono", "Georgia")
AUTOSAVE_DELAY_MS = 650
SEARCH_DELAY_MS = 180
NARROW_WIDTH = 1060
WELCOME_TITLE = "Welcome to your vault"
WELCOME_BODY = (
    "# Your notes, connected\n\n"
    "Write in Markdown. Headings, **bold**, *italic*, ==highlights==, `code`, tables and [[wiki links]] format as you type.\n\n"
    "| Shortcut | Action |\n"
    "| :--- | :--- |\n"
    "| `Ctrl+N` | New note |\n"
    "| `Ctrl+Shift+N` | New folder |\n"
    "| `Ctrl+F` | Search |\n"
    "| `Ctrl+E` | Toggle Live Preview / Source |\n"
    "| `Ctrl+R` | Toggle Reading / Editing mode |\n"
    "| `Ctrl+L` | Lock vault |\n\n"
    "- [x] Local-first encrypted storage\n"
    "- [ ] Create a note or link with [[Note title]]\n"
)

TreeKey = tuple[str, int]  # ("note" | "folder", id)


class MainView(ctk.CTkFrame):
    """Three-pane workspace: file tree, editor and backlinks."""

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=Colors.bg, corner_radius=0)
        self.controller = controller
        self.vault: Vault | None = None
        self.note_id: int | None = None
        self.folder_id = 0                      # folder of the open note
        self.selection: TreeKey | None = None   # highlighted tree item
        self.expanded_folders: set[int] = set()
        self._all_notes = []
        self._folders = []
        self._note_links: dict[int, set[str]] = {}
        self._rows: dict[TreeKey, tuple[ctk.CTkFrame, ctk.CTkLabel]] = {}
        self._hover_key: TreeKey | None = None
        self._save_job = None
        self._search_job = None
        self._saved_title = ""
        self._editor_family = cf.get_preference("editor_font", EDITOR_FONTS[0])
        if self._editor_family not in EDITOR_FONTS:
            self._editor_family = EDITOR_FONTS[0]
        self._context_visible = True
        self._auto_collapsed = False
        self.settings_dialog: Dialog | None = None
        self._build()
        self._bind_shortcuts()

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self._build_sidebar()
        ctk.CTkFrame(self, width=1, corner_radius=0, fg_color=Colors.border).grid(row=0, column=1, sticky="ns")
        self._build_editor()
        self.context_divider = ctk.CTkFrame(self, width=1, corner_radius=0, fg_color=Colors.border)
        self.context_divider.grid(row=0, column=3, sticky="ns")
        self._build_context_panel()
        self.bind("<Configure>", self._on_resize, add="+")

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, width=Metrics.sidebar_width, fg_color=Colors.sidebar, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(side, fg_color="transparent", height=48)
        header.grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=(8, 0))
        header.grid_columnconfigure(1, weight=1)
        self.logo = logo_image(22)
        ctk.CTkLabel(header, text="", image=self.logo, width=22).grid(row=0, column=0, padx=(0, 8))
        self.vault_label = ctk.CTkLabel(header, text="Vault", font=Fonts.body_bold, text_color=Colors.text, anchor="w")
        self.vault_label.grid(row=0, column=1, sticky="ew")
        icon_button(header, "note_plus", self.new_note, "New note  (Ctrl+N)", size=28, icon_size=16).grid(
            row=0, column=2)
        icon_button(header, "folder_plus", lambda: self.new_folder(), "New folder  (Ctrl+Shift+N)", size=28,
                    icon_size=16).grid(row=0, column=3)

        search_box = ctk.CTkFrame(side, fg_color=Colors.input_bg, border_width=1, border_color=Colors.border,
                                  corner_radius=Metrics.radius, height=32)
        search_box.grid(row=1, column=0, sticky="ew", padx=12, pady=(6, 8))
        search_box.pack_propagate(False)
        ctk.CTkLabel(search_box, text="", image=icon_image("search", 14, "faint"), width=16).pack(side="left",
                                                                                                padx=(9, 2))
        self.search = ctk.CTkEntry(search_box, placeholder_text="Search  (Ctrl+F)", border_width=0,
                                   fg_color="transparent", text_color=Colors.text, font=Fonts.body,
                                   placeholder_text_color=Colors.text_faint, height=28)
        self.search.pack(side="left", fill="both", expand=True, padx=(0, 6), pady=1)
        self.search.bind("<KeyRelease>", self.queue_search)
        self.search.bind("<Escape>", lambda _e: (self.search.delete(0, "end"), self.refresh_tree()))

        self.tree = ctk.CTkScrollableFrame(side, fg_color="transparent", corner_radius=0,
                                           scrollbar_button_color=Colors.border,
                                           scrollbar_button_hover_color=Colors.text_faint)
        self.tree.grid(row=2, column=0, sticky="nsew", padx=(4, 0))
        self.tree.bind("<Button-1>", lambda _e: self._select(None))
        self.tree.bind("<Button-3>", lambda e: self._show_context_menu(e, None))
        self.row_action = icon_button(self.tree, "trash", self._delete_hovered, "Delete", size=22, icon_size=14)

        ctk.CTkFrame(side, height=1, corner_radius=0, fg_color=Colors.border).grid(row=3, column=0, sticky="ew")
        footer = ctk.CTkFrame(side, fg_color="transparent", height=44)
        footer.grid(row=4, column=0, sticky="ew", padx=8, pady=6)
        icon_button(footer, "settings", self.show_settings, "Settings  (Ctrl+,)").pack(side="left")
        icon_button(footer, "theme", self.toggle_theme, "Toggle light / dark").pack(side="left", padx=(2, 0))
        icon_button(footer, "export", lambda: self.export_vault_zip(0), "Export vault as .zip").pack(
            side="left", padx=(2, 0))
        icon_button(footer, "lock", self.lock, "Lock vault  (Ctrl+L)").pack(side="right")

    def _build_editor(self) -> None:
        center = ctk.CTkFrame(self, fg_color=Colors.bg, corner_radius=0)
        center.grid(row=0, column=2, sticky="nsew")
        center.grid_rowconfigure(2, weight=1)
        center.grid_columnconfigure(0, weight=1)

        bar = ctk.CTkFrame(center, fg_color="transparent", height=44)
        bar.grid(row=0, column=0, sticky="ew", padx=(28, 12), pady=(6, 0))
        bar.grid_columnconfigure(0, weight=1)
        self.breadcrumb = ctk.CTkLabel(bar, text="", font=Fonts.small, text_color=Colors.text_sub, anchor="w")
        self.breadcrumb.grid(row=0, column=0, sticky="ew")
        self.status = ctk.CTkLabel(bar, text="", font=Fonts.small, text_color=Colors.text_faint)
        self.status.grid(row=0, column=1, padx=(8, 8))
        self.delete_button = icon_button(bar, "trash", self.delete_current_note, "Delete note")
        self.delete_button.grid(row=0, column=2)
        self.reading_mode_button = icon_button(
            bar, "book", self.toggle_reading_mode, "Toggle reading mode  (Ctrl+R)"
        )
        self.reading_mode_button.grid(row=0, column=3, padx=(2, 0))
        icon_button(bar, "panel_right", self.toggle_context_panel, "Toggle backlinks panel").grid(
            row=0, column=4, padx=(2, 0))

        self.title = ctk.CTkEntry(center, placeholder_text="Untitled", font=Fonts.title, border_width=0,
                                  fg_color="transparent", text_color=Colors.text,
                                  placeholder_text_color=Colors.text_faint, height=48)
        self.title.grid(row=1, column=0, sticky="ew", padx=(24, 28), pady=(4, 2))
        self.title.bind("<KeyRelease>", self.queue_save)
        self.title.bind("<Return>", lambda _e: (self.editor.focus_set(), "break")[1])

        self.editor = ctk.CTkTextbox(center, wrap="word", font=(self._editor_family, 15), fg_color=Colors.bg,
                                     text_color=Colors.text, border_width=0, corner_radius=0,
                                     scrollbar_button_color=Colors.border,
                                     scrollbar_button_hover_color=Colors.text_faint)
        self.editor.grid(row=2, column=0, sticky="nsew", padx=(24, 8), pady=(0, 12))
        text = self.editor._textbox
        text.configure(spacing1=2, spacing3=4, padx=4, undo=True, maxundo=250, autoseparators=True)
        self.empty_hint = ctk.CTkLabel(self.editor, text="Start writing — Markdown formats as you type.",
                                       font=Fonts.body, text_color=Colors.text_faint)
        self.empty_hint.bind("<Button-1>", lambda _e: self.editor.focus_set())
        self.md_controller = MarkdownEditorController(
            self.editor,
            on_open_wikilink=self._open_wikilink_target,
            on_modified=self.queue_save,
            font_family=self._editor_family,
        )
        self.editor.bind("<KeyRelease>", self.queue_save)
        self.editor.bind("<KeyRelease>", self._update_empty_hint, add="+")
        self.editor.bind("<Control-s>", self.save)
        self.title.bind("<Control-s>", self.save)

        self.empty_state = ctk.CTkFrame(center, fg_color=Colors.bg, corner_radius=0)
        ctk.CTkLabel(self.empty_state, text="", image=icon_image("note", 40, "faint")).pack(pady=(0, 12))
        ctk.CTkLabel(self.empty_state, text="No note open", font=Fonts.header, text_color=Colors.text).pack()
        ctk.CTkLabel(self.empty_state, text="Select a note in the sidebar or create a new one.",
                     font=Fonts.body, text_color=Colors.text_sub).pack(pady=(4, 16))
        primary_button(self.empty_state, "New note", self.new_note, width=120).pack()

    def _build_context_panel(self) -> None:
        self.context_panel = ctk.CTkFrame(self, width=Metrics.context_width, fg_color=Colors.sidebar,
                                          corner_radius=0)
        self.context_panel.grid(row=0, column=4, sticky="nsew")
        self.context_panel.grid_propagate(False)
        self.context_panel.grid_columnconfigure(0, weight=1)
        self.context_panel.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self.context_panel, text="BACKLINKS", font=Fonts.section, text_color=Colors.text_faint,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=18, pady=(20, 8))
        self.side = ctk.CTkScrollableFrame(self.context_panel, fg_color="transparent", corner_radius=0,
                                           scrollbar_button_color=Colors.border,
                                           scrollbar_button_hover_color=Colors.text_faint)
        self.side.grid(row=1, column=0, sticky="nsew", padx=(6, 0), pady=(0, 8))

    # -------------------------------------------------------------- shortcuts
    def _bind_shortcuts(self) -> None:
        root = self.controller
        shortcuts = {
            "<Control-n>": self.new_note,
            "<Control-N>": lambda: self.new_folder(),
            "<Control-f>": self._focus_search,
            "<Control-e>": self.toggle_editor_mode,
            "<Control-r>": self.toggle_reading_mode,
            "<Control-l>": self.lock,
            "<Control-comma>": self.show_settings,
        }
        for sequence, action in shortcuts.items():
            root.bind(sequence, lambda _e, action=action: self._run_shortcut(action), add="+")

    def _run_shortcut(self, action):
        if self.vault is None or self.controller.focus_get() is None:
            return None
        if self.settings_dialog is not None and self.settings_dialog.winfo_exists():
            return None
        action()
        return "break"

    def _focus_search(self) -> None:
        self.search.focus_set()
        self.search.select_range(0, "end")

    # ------------------------------------------------------------- lifecycle
    @staticmethod
    def _release_memory() -> None:
        """Collect cyclic garbage and return unused heap/working-set pages to the OS."""
        gc.collect()
        if sys.platform.startswith("win"):
            try:
                ctypes.cdll.msvcrt._heapmin()
                k32 = ctypes.WinDLL("kernel32")
                k32.GetCurrentProcess.restype = ctypes.c_void_p
                ctypes.WinDLL("psapi").EmptyWorkingSet(ctypes.c_void_p(k32.GetCurrentProcess()))
            except (AttributeError, OSError):
                pass

    def _set_title_text(self, value: str) -> None:
        was_readonly = self.md_controller.reading_mode
        if was_readonly:
            self.title.configure(state="normal")
        self.title.delete(0, "end")
        if value:
            self.title.insert(0, value)
        if was_readonly:
            self.title.configure(state="readonly")

    def _set_editor_text(self, content: str) -> None:
        """Replace editor text without recording full-document copies in Tcl's undo stack."""
        tb = self.editor._textbox
        tb.configure(state="normal", undo=False)
        try:
            self.editor.delete("1.0", "end")
            if content:
                self.editor.insert("1.0", content)
            tb.edit_reset()
        finally:
            tb.configure(
                undo=True,
                state="disabled" if self.md_controller.reading_mode else "normal",
                insertwidth=0 if self.md_controller.reading_mode else 2,
            )

    def update_view(self, context=None) -> None:
        if not context:
            return
        if self.vault:
            self.lock(navigate=False)
        try:
            self.vault = Vault(context["vault_name"], context["password"])
        except (KeyError, ValueError):
            self.vault = None
            self.controller.show_frame("WelcomeView")
            return
        self.vault_label.configure(text=self.vault.name)
        self.note_id = None
        self.selection = None
        self.search.delete(0, "end")
        self.expanded_folders = set()
        self._reload()
        if not self._all_notes and not self._folders:
            self.vault.create_note(WELCOME_TITLE, WELCOME_BODY)
            self._reload()
        self.refresh_tree()
        recent = self._all_notes[0].id if self._all_notes else None
        if recent is not None:
            self.open_note(recent)
        else:
            self._show_empty_state()
        self._apply_editor_theme()

    def lock(self, navigate: bool = True) -> None:
        """Save, close the vault and drop decrypted content from the UI."""
        if self.vault is None:
            return
        self.save()
        for job in (self._save_job, self._search_job):
            if job:
                self.after_cancel(job)
        self._save_job = self._search_job = None
        if self.settings_dialog is not None and self.settings_dialog.winfo_exists():
            self.settings_dialog.close()
        self.vault.close()
        self.vault = None
        self.note_id = None
        self.selection = None
        self._all_notes, self._folders = [], []
        self._note_links.clear()
        self.set_reading_mode(False, announce=False)
        self.md_controller.reset()
        self._set_title_text("")
        self._set_editor_text("")
        self.search.delete(0, "end")
        self._clear_tree()
        for child in self.side.winfo_children():
            child.destroy()
        self._release_memory()
        if navigate:
            self.controller.show_frame("WelcomeView")

    # ------------------------------------------------------------------ data
    def _reload(self) -> None:
        self._all_notes = self.vault.notes() if self.vault else []
        self._folders = list(self.vault.folders()) if self.vault else []
        self._note_links = {
            note.id: {link.casefold() for link in Vault.links(note.content)}
            for note in self._all_notes
        }

    def _note(self, note_id: int | None):
        return next((note for note in self._all_notes if note.id == note_id), None)

    def _folder(self, folder_id: int):
        return next((folder for folder in self._folders if folder.id == folder_id), None)

    def _folder_path(self, folder_id: int) -> list[str]:
        names, seen = [], set()
        while folder_id and folder_id not in seen:
            seen.add(folder_id)
            folder = self._folder(folder_id)
            if folder is None:
                break
            names.append(folder.name)
            folder_id = folder.parent_id
        return list(reversed(names))

    def _target_folder(self) -> int:
        """Folder where new notes/folders go, based on the current selection."""
        if self.selection is None:
            return 0
        kind, item_id = self.selection
        if kind == "folder":
            return item_id
        note = self._note(item_id)
        return note.folder_id if note else 0

    def _expand_to(self, folder_id: int) -> None:
        seen = set()
        while folder_id and folder_id not in seen:
            seen.add(folder_id)
            self.expanded_folders.add(folder_id)
            folder = self._folder(folder_id)
            folder_id = folder.parent_id if folder else 0

    # ------------------------------------------------------------------ tree
    def _clear_tree(self) -> None:
        self.row_action.place_forget()
        for child in self.tree.winfo_children():
            if child is not self.row_action:
                child.destroy()
        self._rows.clear()
        self._hover_key = None

    def refresh_tree(self) -> None:
        self._clear_tree()
        if not self.vault:
            return
        query = self.search.get().strip().casefold()
        if query:
            self._render_search_results(query)
        else:
            self._render_hierarchy()
        self.row_action.lift()

    def _render_hierarchy(self) -> None:
        children: dict[int, list] = {}
        for folder in self._folders:
            children.setdefault(folder.parent_id, []).append(folder)
        notes_by_folder: dict[int, list] = {}
        for note in self._all_notes:
            notes_by_folder.setdefault(note.folder_id, []).append(note)
        known_folders = {folder.id for folder in self._folders}

        def render(parent_id: int, depth: int) -> None:
            for folder in sorted(children.get(parent_id, []), key=lambda item: item.name.casefold()):
                expanded = folder.id in self.expanded_folders
                self._make_row(("folder", folder.id), depth, folder.name, "folder",
                               "chevron_down" if expanded else "chevron_right")
                if expanded:
                    render(folder.id, depth + 1)
            notes = notes_by_folder.get(parent_id, [])
            if parent_id == 0:  # notes whose folder no longer exists stay reachable at the root
                notes = notes + [n for fid, items in notes_by_folder.items() if fid and fid not in known_folders
                                 for n in items]
            for note in sorted(notes, key=lambda item: (item.title or "Untitled").casefold()):
                self._make_row(("note", note.id), depth, note.title or "Untitled", "note")

        render(0, 0)
        if not self._rows:
            ctk.CTkLabel(self.tree, text="This vault is empty.", font=Fonts.small, text_color=Colors.text_faint,
                         anchor="w").pack(fill="x", padx=12, pady=8)

    def _render_search_results(self, query: str) -> None:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        matches = [note for note in self._all_notes
                   if query in note.title.casefold() or pattern.search(note.content) is not None]
        if not matches:
            ctk.CTkLabel(self.tree, text="No matching notes", font=Fonts.small, text_color=Colors.text_faint,
                         anchor="w").pack(fill="x", padx=12, pady=8)
            return
        for note in sorted(matches, key=lambda item: item.title.casefold()):
            path = " / ".join(self._folder_path(note.folder_id))
            self._make_row(("note", note.id), 0, note.title or "Untitled", "note", hint=path)

    def _make_row(self, key: TreeKey, depth: int, text: str, icon: str, chevron: str | None = None,
                  hint: str = "") -> None:
        row = ctk.CTkFrame(self.tree, height=Metrics.row_height, corner_radius=Metrics.radius - 2,
                           fg_color="transparent")
        row.pack(fill="x", padx=(0, 6), pady=0)
        row.pack_propagate(False)
        for level in range(depth):
            ctk.CTkFrame(row, width=1, corner_radius=0, fg_color=Colors.guide).place(
                x=13 + level * Metrics.indent, y=0, relheight=1)
        indent = 4 + depth * Metrics.indent
        parts = []
        if chevron:
            chevron_label = ctk.CTkLabel(row, text="", image=icon_image(chevron, 14, "faint"), width=18)
            chevron_label.pack(side="left", padx=(indent, 0))
            parts.append(chevron_label)
        else:
            ctk.CTkFrame(row, width=18, height=1, fg_color="transparent").pack(side="left", padx=(indent, 0))
        icon_label = ctk.CTkLabel(row, text="", image=icon_image(icon, 15), width=20)
        icon_label.pack(side="left", padx=(0, 4))
        label = ctk.CTkLabel(row, text=text, font=Fonts.body, text_color=Colors.text, anchor="w")
        label.pack(side="left", fill="x", expand=True, padx=(0, 28))
        parts += [icon_label, label]
        if hint:
            label.configure(text=f"{text}   ")
            hint_label = ctk.CTkLabel(row, text=hint, font=Fonts.small, text_color=Colors.text_faint, anchor="e")
            hint_label.place(relx=1, x=-30, rely=0.5, anchor="e")
            parts.append(hint_label)
        for widget in (row, *parts):
            widget.bind("<Button-1>", lambda _e, key=key: self._on_row_click(key))
            widget.bind("<Button-3>", lambda e, key=key: self._show_context_menu(e, key))
            widget.bind("<Enter>", lambda _e, key=key: self._on_row_enter(key))
            widget.bind("<Leave>", lambda _e, key=key: self._on_row_leave(key))
        self._rows[key] = (row, label)
        self._paint_row(key)

    def _paint_row(self, key: TreeKey) -> None:
        if key not in self._rows:
            return
        row, label = self._rows[key]
        if key == self.selection:
            color = Colors.selected
        elif key == ("note", self.note_id):
            color = Colors.active
        elif key == self._hover_key:
            color = Colors.hover
        else:
            color = "transparent"
        row.configure(fg_color=color)
        label.configure(font=Fonts.body_bold if key == ("note", self.note_id) else Fonts.body)

    def _repaint_rows(self) -> None:
        for key in self._rows:
            self._paint_row(key)

    def _on_row_enter(self, key: TreeKey) -> None:
        if self._hover_key != key:
            previous, self._hover_key = self._hover_key, key
            if previous:
                self._paint_row(previous)
            self._paint_row(key)
        row, _ = self._rows[key]
        self.row_action.place(in_=row, relx=1, x=-4, rely=0.5, anchor="e")
        self.row_action.lift()

    def _on_row_leave(self, key: TreeKey) -> None:
        self.after(15, lambda: self._check_hover(key))

    def _check_hover(self, key: TreeKey) -> None:
        if key not in self._rows or self._hover_key != key:
            return
        row, _ = self._rows[key]
        pointer = row.winfo_containing(*row.winfo_pointerxy())
        name = str(pointer) if pointer is not None else ""
        if name.startswith(str(row)) or name.startswith(str(self.row_action)):
            return
        self._hover_key = None
        self.row_action.place_forget()
        self._paint_row(key)

    def _on_row_click(self, key: TreeKey) -> str:
        kind, item_id = key
        if kind == "folder":
            self._select(key)
            self.toggle_folder(item_id)
        else:
            self.open_note(item_id)
        return "break"

    def _select(self, key: TreeKey | None) -> None:
        previous, self.selection = self.selection, key
        for item in (previous, key):
            if item:
                self._paint_row(item)

    def toggle_folder(self, folder_id: int) -> None:
        self.expanded_folders.symmetric_difference_update({folder_id})
        self.refresh_tree()

    def _delete_hovered(self) -> None:
        key = self._hover_key
        if key is None:
            return
        if key[0] == "note":
            self.delete_note(key[1])
        else:
            self.delete_folder(key[1])

    def _show_context_menu(self, event, key: TreeKey | None) -> str:
        if not self.vault:
            return "break"
        if key is not None:
            self._select(key)
        else:
            self._select(None)
        menu = tk.Menu(self, tearoff=0, bg=resolve(Colors.card), fg=resolve(Colors.text),
                       activebackground=resolve(Colors.selected), activeforeground=resolve(Colors.text),
                       bd=0, relief="flat", font=Fonts.body)
        if key is None or key[0] == "folder":
            parent = key[1] if key else 0
            menu.add_command(label="New note", command=lambda: self.new_note(parent))
            menu.add_command(label="New folder", command=lambda: self.new_folder(parent))
            if key:
                expanded = key[1] in self.expanded_folders
                menu.add_command(label="Collapse" if expanded else "Expand",
                                 command=lambda: self.toggle_folder(key[1]))
                menu.add_separator()
                menu.add_command(label="Export folder as .zip…", command=lambda: self.export_vault_zip(key[1]))
                menu.add_command(label="Delete folder…", command=lambda: self.delete_folder(key[1]))
            else:
                menu.add_separator()
                menu.add_command(label="Export vault as .zip…", command=lambda: self.export_vault_zip(0))
        else:
            menu.add_command(label="Open", command=lambda: self.open_note(key[1]))
            menu.add_separator()
            menu.add_command(label="Delete note…", command=lambda: self.delete_note(key[1]))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    # ---------------------------------------------------------------- search
    def queue_search(self, _event=None) -> None:
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(SEARCH_DELAY_MS, self._run_search)

    def _run_search(self) -> None:
        self._search_job = None
        self.refresh_tree()

    # ----------------------------------------------------------------- notes
    def open_note(self, note_id: int) -> None:
        if not self.vault:
            return
        if note_id == self.note_id and self._note(note_id) is not None:
            return
        self.save()
        if not self._all_notes:
            self._reload()
        note = self._note(note_id)
        if not note:
            self._reload()
            note = self._note(note_id)
            if not note:
                return
        prev_note = self._note(self.note_id)
        was_large = prev_note is not None and len(prev_note.content) > 200_000
        self.note_id = note.id
        self.folder_id = note.folder_id
        self._saved_title = note.title
        self.empty_state.grid_forget()
        self._set_title_text(note.title)
        self.md_controller.reset()
        self._set_editor_text(note.content)
        if was_large:
            self._release_memory()
        self.editor.mark_set("insert", "1.0")
        self.editor.see("1.0")
        self.render_markdown()
        if self.md_controller.reading_mode:
            self.status.configure(text="Reading mode", text_color=Colors.primary)
        else:
            self.status.configure(text=f"Edited {note.updated_at}" if note.updated_at else "", text_color=Colors.text_faint)
        self._update_breadcrumb()
        previous_expanded = set(self.expanded_folders)
        self._expand_to(note.folder_id)
        self.selection = ("note", note.id)
        if previous_expanded != self.expanded_folders or ("note", note.id) not in self._rows:
            self.refresh_tree()
        else:
            self._repaint_rows()
        self.show_backlinks()

    def _show_empty_state(self) -> None:
        self.note_id = None
        self.md_controller.reset()
        self._set_title_text("")
        self._set_editor_text("")
        self.breadcrumb.configure(text="")
        self.status.configure(text="")
        self.empty_state.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self.empty_state.lift()
        self.show_backlinks()

    def _update_breadcrumb(self) -> None:
        parts = [self.vault.name if self.vault else "", *self._folder_path(self.folder_id)]
        self.breadcrumb.configure(text="  /  ".join(part for part in parts if part))

    def new_note(self, folder_id: int | None = None) -> None:
        if not self.vault:
            return
        if self.md_controller.reading_mode:
            self.set_reading_mode(False, announce=False)
        self.save()
        folder_id = self._target_folder() if folder_id is None else folder_id
        existing = {note.title.casefold() for note in self._all_notes}
        title, number = "Untitled", 1
        while title.casefold() in existing:
            number += 1
            title = f"Untitled {number}"
        note_id = self.vault.create_note(title, folder_id=folder_id)
        self._reload()
        self._expand_to(folder_id)
        self.refresh_tree()
        self.open_note(note_id)
        self.title.focus_set()
        self.title.select_range(0, "end")

    def delete_current_note(self) -> None:
        if self.note_id:
            self.delete_note(self.note_id)

    def delete_note(self, note_id: int) -> None:
        note = self._note(note_id)
        if not note:
            return
        title = note.title or "Untitled"
        confirm(self, "Delete note", f"“{title}” will be permanently deleted.", "Delete",
                lambda: self._delete_note_now(note_id))

    def _delete_note_now(self, note_id: int) -> None:
        if not self.vault:
            return
        if note_id == self.note_id:
            self._cancel_save()
            self.note_id = None
        self.vault.delete_note(note_id)
        if self.selection == ("note", note_id):
            self.selection = None
        self._reload()
        self.refresh_tree()
        if self.note_id is None:
            self._open_fallback_note()
        self._release_memory()
        self.status.configure(text="Note deleted", text_color=Colors.text_faint)

    def _open_fallback_note(self) -> None:
        if self._all_notes:
            self.open_note(self._all_notes[0].id)
        else:
            self._show_empty_state()

    # --------------------------------------------------------------- folders
    def new_folder(self, parent_id: int | None = None) -> None:
        """Create a folder through an in-app dialog with live duplicate checks."""
        if not self.vault:
            return
        parent_id = self._target_folder() if parent_id is None else parent_id
        location = " / ".join(self._folder_path(parent_id)) or self.vault.name
        dialog = Dialog(self, "New folder")
        dialog.heading("New folder", f"Inside {location}")
        name = text_entry(dialog.body, "Folder name")
        name.pack(fill="x", pady=(16, 0))
        validation = ctk.CTkLabel(dialog.body, text="", font=Fonts.small, text_color=Colors.error, anchor="w",
                                  height=18)
        validation.pack(fill="x", pady=(4, 0))
        row = dialog.actions()
        create_button = primary_button(row, "Create", lambda: create(), width=96)
        create_button.pack(side="right")
        secondary_button(row, "Cancel", dialog.close, width=86).pack(side="right", padx=(0, 8))

        def problem() -> str:
            value = name.get().strip()
            if not value:
                return ""
            if self.vault.folder_name_exists(value, parent_id):
                return f"A folder named “{value}” already exists here."
            return ""

        def validate(_event=None) -> None:
            message = problem()
            validation.configure(text=message)
            name.configure(border_color=Colors.error if message else Colors.border)
            create_button.configure(state="disabled" if message or not name.get().strip() else "normal")

        def create() -> None:
            validate()
            if create_button.cget("state") == "disabled":
                return
            try:
                folder_id = self.vault.create_folder(name.get(), parent_id)
            except DuplicateNameError as error:
                validation.configure(text=str(error))
                return
            except ValueError as error:
                validation.configure(text=str(error))
                return
            dialog.close()
            self._reload()
            self._expand_to(parent_id)
            self.expanded_folders.add(folder_id)
            self.selection = ("folder", folder_id)
            self.refresh_tree()

        name.bind("<KeyRelease>", validate)
        name.bind("<Return>", lambda _e: create())
        dialog.validate = validate
        validate()
        dialog.present()
        dialog.after(60, name.focus_set)

    def delete_folder(self, folder_id: int) -> None:
        folder = self._folder(folder_id)
        if not folder or not self.vault:
            return
        ids = set(self.vault.descendant_folder_ids(folder_id))
        note_count = sum(1 for note in self._all_notes if note.folder_id in ids)
        sub_count = len(ids) - 1
        details = []
        if note_count:
            details.append(f"{note_count} note{'s' if note_count != 1 else ''}")
        if sub_count:
            details.append(f"{sub_count} sub-folder{'s' if sub_count != 1 else ''}")
        contents = f" and {' and '.join(details)} inside it" if details else ""
        confirm(self, "Delete folder", f"“{folder.name}”{contents} will be permanently deleted.", "Delete",
                lambda: self._delete_folder_now(folder_id, ids))

    def _delete_folder_now(self, folder_id: int, ids: set[int]) -> None:
        if not self.vault:
            return
        open_note = self._note(self.note_id)
        if open_note and open_note.folder_id in ids:
            self._cancel_save()
            self.note_id = None
        self.vault.delete_folder(folder_id)
        self.expanded_folders -= ids
        if self.selection and self.selection[0] == "folder" and self.selection[1] in ids:
            self.selection = None
        self._reload()
        self.refresh_tree()
        if self.note_id is None:
            self._open_fallback_note()
        self._release_memory()
        self.status.configure(text="Folder deleted", text_color=Colors.text_faint)

    # ------------------------------------------------------------------ save
    def queue_save(self, event=None) -> None:
        if self.note_id is None or self.md_controller.reading_mode or (
            event is not None
            and event.keysym
            in {
                "Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R",
                "Up", "Down", "Left", "Right", "Prior", "Next", "Home", "End",
                "Escape", "Caps_Lock",
            }
        ):
            return
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save_job = self.after(AUTOSAVE_DELAY_MS, self.save)
        self.status.configure(text="Editing…", text_color=Colors.text_faint)

    def _cancel_save(self) -> None:
        if self._save_job:
            self.after_cancel(self._save_job)
            self._save_job = None

    def save(self, _event=None):
        self._cancel_save()
        if not (self.vault and self.note_id):
            return "break"
        title = self.title.get().strip() or "Untitled"
        content = self.editor.get("1.0", "end-1c")
        note = self._note(self.note_id)
        if note and note.title == title and note.content == content:
            return "break"
        self.vault.save_note(self.note_id, title, content, self.folder_id)
        updated = Note(
            self.note_id,
            self.folder_id,
            title,
            content,
            note.is_markdown if note else True,
            note.created_at if note else "",
            note.updated_at if note else "",
        )
        self._all_notes = [updated if item.id == self.note_id else item for item in self._all_notes]
        self._note_links[self.note_id] = {link.casefold() for link in Vault.links(content)}
        duplicate = any(other.id != self.note_id and other.title.casefold() == title.casefold()
                        for other in self._all_notes)
        if duplicate:
            self.status.configure(text="Another note has this title", text_color=Colors.error)
        else:
            self.status.configure(text="Saved", text_color=Colors.text_faint)
        if title != self._saved_title:
            self._saved_title = title
            if ("note", self.note_id) in self._rows:
                self._rows[("note", self.note_id)][1].configure(text=title)
            self.show_backlinks()
        return "break"

    # ------------------------------------------------------------- markdown
    def _update_empty_hint(self, _event=None) -> None:
        if (
            self.note_id is None
            or self.md_controller.reading_mode
            or self.editor._textbox.compare("end-1c", ">", "1.200")
            or self.editor.get("1.0", "1.200").strip()
        ):
            self.empty_hint.place_forget()
        else:
            self.empty_hint.place(relx=0.5, rely=0.3, anchor="center")

    def render_markdown(self, _event=None) -> None:
        self._update_empty_hint()
        self.md_controller.render()

    def _apply_editor_theme(self) -> None:
        """Re-resolve plain-Tk colours that CustomTkinter does not manage."""
        self.md_controller.set_font_family(self._editor_family)
        self.md_controller.apply_theme()
        self.render_markdown()

    def toggle_editor_mode(self) -> None:
        if self.md_controller.reading_mode:
            self.set_reading_mode(False, announce=False)
        self.md_controller.set_live_preview(not self.md_controller.live_preview)
        mode_label = "Live Preview" if self.md_controller.live_preview else "Source mode"
        self.status.configure(text=mode_label, text_color=Colors.text_faint)

    def toggle_reading_mode(self) -> None:
        self.set_reading_mode(not self.md_controller.reading_mode)

    def set_reading_mode(self, enabled: bool, announce: bool = True) -> None:
        if enabled:
            self.save()
        self.title.configure(state="readonly" if enabled else "normal")
        self.md_controller.set_reading_mode(enabled)
        self.reading_mode_button.configure(
            image=icon_image("book", 17, "primary" if enabled else "muted"),
            fg_color=Colors.selected if enabled else "transparent",
        )
        self._update_empty_hint()
        if announce and self.note_id is not None:
            if enabled:
                self.status.configure(text="Reading mode", text_color=Colors.primary)
            else:
                self.status.configure(text="Editing", text_color=Colors.text_faint)

    def _open_wikilink_target(self, raw_target: str) -> None:
        """Open the vault note targeted by a clicked wiki link."""
        target = raw_target.strip().casefold()
        note = next((item for item in self._all_notes if item.title.casefold() == target), None)
        if note:
            self.open_note(note.id)
        else:
            self.status.configure(text=f"No note named “{raw_target.strip()}”", text_color=Colors.text_faint)

    def show_backlinks(self) -> None:
        for child in self.side.winfo_children():
            child.destroy()
        if not self.vault or not self.note_id:
            return
        title = self.title.get().strip()
        wanted = title.casefold()
        links = [
            note for note in self._all_notes
            if note.id != self.note_id and wanted in self._note_links.get(note.id, set())
        ]
        if not links:
            ctk.CTkLabel(self.side, text="No other notes link here yet.", font=Fonts.small,
                         text_color=Colors.text_sub, anchor="w", justify="left", wraplength=190).pack(
                fill="x", padx=12, pady=(0, 4))
            ctk.CTkLabel(self.side, text=f"Use [[{title or 'Note title'}]] in another note.", font=Fonts.small,
                         text_color=Colors.text_faint, anchor="w", justify="left", wraplength=190).pack(
                fill="x", padx=12)
            return
        for note in links:
            button = ctk.CTkButton(self.side, text=note.title, image=icon_image("note", 14), compound="left",
                                   anchor="w", height=28, corner_radius=Metrics.radius - 2, font=Fonts.body,
                                   fg_color="transparent", hover_color=Colors.hover, text_color=Colors.text,
                                   command=lambda note_id=note.id: self.open_note(note_id))
            button.pack(fill="x", padx=(6, 8), pady=1)

    # ------------------------------------------------------ panel & theming
    def toggle_context_panel(self) -> None:
        self._auto_collapsed = False
        self._set_context_visible(not self._context_visible)

    def _set_context_visible(self, visible: bool) -> None:
        self._context_visible = visible
        if visible:
            self.context_divider.grid()
            self.context_panel.grid()
        else:
            self.context_divider.grid_remove()
            self.context_panel.grid_remove()

    def _on_resize(self, _event=None) -> None:
        logical = self.winfo_width() / ctk.ScalingTracker.get_widget_scaling(self)
        if logical <= 1:  # not mapped yet
            return
        if logical < NARROW_WIDTH and self._context_visible:
            self._auto_collapsed = True
            self._set_context_visible(False)
        elif logical >= NARROW_WIDTH and self._auto_collapsed:
            self._auto_collapsed = False
            self._set_context_visible(True)

    def toggle_theme(self) -> None:
        self.change_theme("Light" if ctk.get_appearance_mode() == "Dark" else "Dark")

    def change_theme(self, value: str) -> None:
        ctk.set_appearance_mode(value.lower())
        cf.set_preference("theme", value.lower())
        self.after(20, self._apply_editor_theme)

    def change_color_theme(self, value: str) -> None:
        palette = apply_color_theme(value)
        cf.set_preference("color_theme", palette)
        self.after(20, self._apply_editor_theme)

    def change_editor_font(self, family: str) -> None:
        self._editor_family = family
        self.editor.configure(font=(family, 15))
        cf.set_preference("editor_font", family)
        self._apply_editor_theme()

    # -------------------------------------------------------------- settings
    def show_settings(self) -> None:
        if not self.vault:
            return
        if self.settings_dialog is not None and self.settings_dialog.winfo_exists():
            self.settings_dialog.reveal()
            return
        dialog = Dialog(self, "Settings", width=380)
        self.settings_dialog = dialog
        dialog.heading("Settings")

        def section(text: str) -> None:
            ctk.CTkLabel(dialog.body, text=text, font=Fonts.section, text_color=Colors.text_faint,
                         anchor="w").pack(fill="x", pady=(18, 6))

        section("APPEARANCE")
        field_label(dialog.body, "Theme").pack(fill="x", pady=(0, 4))
        color_theme = ctk.CTkSegmentedButton(
            dialog.body, values=list(COLOR_THEME_LABELS), command=self.change_color_theme, height=32,
            corner_radius=Metrics.radius, font=Fonts.body, fg_color=Colors.sidebar,
            selected_color=Colors.selected, selected_hover_color=Colors.active,
            unselected_color=Colors.sidebar, unselected_hover_color=Colors.hover, text_color=Colors.text,
        )
        color_theme.set(color_theme_label(cf.get_preference("color_theme", current_color_theme())))
        color_theme.pack(fill="x")

        field_label(dialog.body, "Appearance").pack(fill="x", pady=(12, 4))
        theme = ctk.CTkSegmentedButton(
            dialog.body, values=["Light", "Dark", "System"], command=self.change_theme, height=32,
            corner_radius=Metrics.radius, font=Fonts.body, fg_color=Colors.sidebar,
            selected_color=Colors.selected, selected_hover_color=Colors.active,
            unselected_color=Colors.sidebar, unselected_hover_color=Colors.hover, text_color=Colors.text,
        )
        saved_theme = cf.get_preference("theme", ctk.get_appearance_mode().lower()).capitalize()
        theme.set(saved_theme if saved_theme in {"Light", "Dark", "System"} else ctk.get_appearance_mode())
        theme.pack(fill="x")
        field_label(dialog.body, "Editor font").pack(fill="x", pady=(12, 4))
        font = ctk.CTkOptionMenu(
            dialog.body, values=list(EDITOR_FONTS), command=self.change_editor_font, height=32,
            corner_radius=Metrics.radius, font=Fonts.body, dropdown_font=Fonts.body, fg_color=Colors.input_bg,
            button_color=Colors.input_bg, button_hover_color=Colors.hover, text_color=Colors.text,
            dropdown_fg_color=Colors.card, dropdown_hover_color=Colors.hover, dropdown_text_color=Colors.text,
        )
        font.set(self._editor_family)
        font.pack(fill="x")

        section("IMPORT & EXPORT")
        export_btn = secondary_button(
            dialog.body, "Export vault as .zip…", lambda: self.export_vault_zip(0),
            image=icon_image("export", 15), compound="left", anchor="w",
        )
        export_btn.pack(fill="x", pady=3)
        for label, action in (("Import Markdown file…", self.import_markdown),
                              ("Import folder of notes…", self.import_directory),
                              ("Merge another vault…", self.import_database)):
            button = secondary_button(dialog.body, label, action, image=icon_image("import", 15), compound="left",
                                      anchor="w")
            button.pack(fill="x", pady=3)

        section("UPDATES")
        update_status = ctk.CTkLabel(
            dialog.body,
            text=f"Current version: v{APP_VERSION}",
            font=Fonts.small,
            text_color=Colors.text_sub,
            anchor="w",
            justify="left",
            wraplength=330,
        )
        update_status.pack(fill="x", pady=(0, 6))
        pending_release: list[ReleaseInfo | None] = [None]

        def install_update(release: ReleaseInfo) -> None:
            if not (sys.platform.startswith("win") and release.installer_url):
                webbrowser.open(release.html_url)
                return
            update_btn.configure(state="disabled", text="Downloading update…")
            update_status.configure(text=f"Downloading v{release.version}…", text_color=Colors.text_sub)

            def on_progress(done: int, total: int) -> None:
                if not dialog.winfo_exists():
                    return
                if total > 0:
                    pct = int(done * 100 / total)
                    mb = done / (1024 * 1024)
                    total_mb = total / (1024 * 1024)
                    msg = f"Downloading v{release.version}: {mb:.1f} / {total_mb:.1f} MB ({pct}%)"
                else:
                    msg = f"Downloading v{release.version}: {done / (1024 * 1024):.1f} MB"
                self.after(0, lambda m=msg: update_status.configure(text=m) if dialog.winfo_exists() else None)

            def worker() -> None:
                try:
                    installer_path = download_installer(release, on_progress=on_progress)
                except Exception as exc:
                    err = str(exc) or "Update download failed."
                    self.after(
                        0,
                        lambda: (
                            update_status.configure(text=err, text_color=Colors.error),
                            update_btn.configure(state="normal", text=f"Retry update (v{release.version})"),
                        )
                        if dialog.winfo_exists()
                        else None,
                    )
                    return

                def finish_and_restart() -> None:
                    try:
                        if dialog.winfo_exists():
                            dialog.close()
                        self.lock(navigate=False)
                        launch_windows_installer(installer_path)
                        self.controller.destroy()
                    except Exception as exc:
                        self.status.configure(text=f"Could not launch installer: {exc}", text_color=Colors.error)

                self.after(0, finish_and_restart)

            threading.Thread(target=worker, daemon=True).start()

        def on_update_click() -> None:
            if pending_release[0] is not None:
                install_update(pending_release[0])
                return
            update_btn.configure(state="disabled", text="Checking…")
            update_status.configure(text=f"Checking GitHub Releases (v{APP_VERSION})…", text_color=Colors.text_sub)

            def worker() -> None:
                try:
                    release = check_for_update(APP_VERSION)
                except Exception as exc:
                    err = str(exc) or "Could not check for updates."
                    self.after(
                        0,
                        lambda: (
                            update_status.configure(text=err, text_color=Colors.error),
                            update_btn.configure(state="normal", text="Check for updates"),
                        )
                        if dialog.winfo_exists()
                        else None,
                    )
                    return

                def apply_result() -> None:
                    if not dialog.winfo_exists():
                        return
                    if release is None:
                        update_status.configure(
                            text=f"You are on the latest version (v{APP_VERSION}).",
                            text_color=Colors.success,
                        )
                        update_btn.configure(state="normal", text="Check for updates")
                    else:
                        pending_release[0] = release
                        if sys.platform.startswith("win") and release.installer_url:
                            label = f"Update & Restart (v{release.version})"
                            msg = f"Version {release.version} is ready to install."
                        else:
                            label = f"Download v{release.version}…"
                            msg = f"Version {release.version} is available on GitHub."
                        update_status.configure(text=msg, text_color=Colors.primary)
                        update_btn.configure(state="normal", text=label)

                self.after(0, apply_result)

            threading.Thread(target=worker, daemon=True).start()

        update_btn = secondary_button(
            dialog.body, "Check for updates", on_update_click,
            image=icon_image("import", 15), compound="left", anchor="w",
        )
        update_btn.pack(fill="x", pady=3)

        row = dialog.actions()
        primary_button(row, "Done", dialog.close, width=96).pack(side="right")
        dialog.present()

    # ---------------------------------------------------------------- import & export
    def export_vault_zip(self, folder_id: int = 0) -> None:
        """Export the vault (or a folder subtree) as a unencrypted Markdown .zip archive."""
        if not self.vault:
            return
        self.save()
        folder = self._folder(folder_id) if folder_id else None
        subject = folder.name if folder else self.vault.name
        default_name = f"{safe_filename(subject)}.zip"
        confirm(
            self,
            f"Export “{subject}” as .zip",
            "This creates an unencrypted .zip archive containing your Markdown notes and folder hierarchy. "
            "Anyone with access to the exported file will be able to read its contents.",
            "Choose location…",
            lambda: self._export_zip_to_file(folder_id, default_name),
            danger=False,
        )

    def _export_zip_to_file(self, folder_id: int, default_name: str) -> None:
        if not self.vault:
            return
        path = filedialog.asksaveasfilename(
            parent=self.winfo_toplevel(),
            title="Export Markdown .zip",
            initialfile=default_name,
            defaultextension=".zip",
            filetypes=[("ZIP archive", "*.zip")],
        )
        if not path:
            return
        try:
            count = self.vault.export_zip(Path(path), folder_id=folder_id)
        except (OSError, ValueError) as error:
            self.status.configure(text=f"Export failed: {error}", text_color=Colors.error)
            return
        self.status.configure(
            text=f"Exported {count} note{'s' if count != 1 else ''} to {Path(path).name}",
            text_color=Colors.text_faint,
        )

    def import_markdown(self) -> None:
        path = filedialog.askopenfilename(parent=self.winfo_toplevel(),
                                          filetypes=[("Markdown", "*.md *.markdown"), ("Text", "*.txt")])
        if not path or not self.vault:
            return
        try:
            source = Path(path)
            note_id = self.vault.create_note(source.stem, source.read_text(encoding="utf-8"), self._target_folder())
        except (OSError, UnicodeError):
            self.status.configure(text="That file could not be read as UTF-8 text.", text_color=Colors.error)
            return
        self._reload()
        self.refresh_tree()
        self.open_note(note_id)

    def import_directory(self) -> None:
        """Import Markdown and text files while preserving directory hierarchy."""
        location = filedialog.askdirectory(parent=self.winfo_toplevel(), title="Import a folder of notes")
        if not location or not self.vault:
            return
        root = Path(location)
        sources = sorted(path for path in root.rglob("*")
                         if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt"})
        if not sources:
            self.status.configure(text="No Markdown or text files in that folder.", text_color=Colors.text_faint)
            return
        base = self._target_folder()
        folders = {(folder.parent_id, folder.name.casefold()): folder.id for folder in self.vault.folders()}
        imported = failed = 0
        for source in sources:
            folder_id = base
            for segment in source.relative_to(root).parent.parts:
                key = (folder_id, segment.casefold())
                if key not in folders:
                    folders[key] = self.vault.create_folder(segment, folder_id)
                folder_id = folders[key]
            try:
                self.vault.create_note(source.stem, source.read_text(encoding="utf-8"), folder_id)
                imported += 1
            except (OSError, UnicodeError):
                failed += 1
        self._reload()
        self._expand_to(base)
        self.refresh_tree()
        message = f"Imported {imported} note{'s' if imported != 1 else ''}"
        if failed:
            message += f", {failed} skipped"
        self.status.configure(text=message, text_color=Colors.text_faint)

    def import_database(self) -> None:
        """Ask for a compatible, encrypted vault and merge it into this vault."""
        path = filedialog.askopenfilename(parent=self.winfo_toplevel(), title="Choose a Secure Notes database",
                                          filetypes=[("Secure Notes database", "*.db")])
        if not path or not self.vault:
            return
        dialog = Dialog(self, "Merge vault")
        dialog.heading("Merge another vault", f"{Path(path).name} is opened read-only and is not changed.")
        password = ctk.CTkEntry(dialog.body, placeholder_text="Source vault password", show="●",
                                height=Metrics.control_height, corner_radius=Metrics.radius,
                                border_color=Colors.border, fg_color=Colors.input_bg, text_color=Colors.text,
                                font=Fonts.body)
        password.pack(fill="x", pady=(16, 4))
        status = ctk.CTkLabel(dialog.body, text="", font=Fonts.small, text_color=Colors.error, anchor="w")
        status.pack(fill="x")

        def merge() -> None:
            if not password.get():
                status.configure(text="Enter the source vault password.")
                return
            try:
                imported, skipped = self.vault.merge_database(Path(path), password.get())
            except (OSError, ValueError) as error:
                status.configure(text=str(error))
                password.delete(0, "end")
                return
            password.delete(0, "end")
            dialog.close()
            self._reload()
            self.refresh_tree()
            self.status.configure(text=f"Merged {imported} note{'s' if imported != 1 else ''}, "
                                       f"skipped {skipped}", text_color=Colors.text_faint)

        row = dialog.actions()
        primary_button(row, "Merge", merge, width=96).pack(side="right")
        secondary_button(row, "Cancel", dialog.close, width=86).pack(side="right", padx=(0, 8))
        password.bind("<Return>", lambda _e: merge())
        dialog.present()
        dialog.after(60, password.focus_set)
