import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

from app.core.vault import Vault
from .styles import Colors, Fonts


class MainView(ctk.CTkFrame):
    """The unlocked, local-first Markdown workspace."""

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=Colors.bg)
        self.controller = controller
        self.vault = None
        self.note_id = None
        self.folder_id = 0
        self._save_job = None
        self._notes = []
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(self, fg_color=Colors.card, corner_radius=0, height=48)
        bar.grid(row=0, column=0, columnspan=3, sticky="ew")
        bar.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(bar, text="SECURE NOTES", font=("Segoe UI", 14, "bold"), text_color=Colors.text).grid(row=0, column=0, padx=18, pady=12)
        ctk.CTkButton(bar, text="+ Note", width=76, height=30, command=self.new_note, fg_color=Colors.primary, hover_color=Colors.primary_hover).grid(row=0, column=1, padx=(0, 8), pady=8)
        self.search = ctk.CTkEntry(bar, placeholder_text="Search notes", width=220, height=30)
        self.search.grid(row=0, column=2, sticky="e", padx=8, pady=8)
        self.search.bind("<KeyRelease>", lambda _event: self.refresh_notes())
        ctk.CTkButton(bar, text="Graph", width=64, height=30, fg_color="transparent", border_width=1, border_color=Colors.border, text_color=Colors.text, command=self.show_graph).grid(row=0, column=3, padx=8, pady=8)

        left = ctk.CTkFrame(self, width=235, fg_color=Colors.card, corner_radius=0)
        left.grid(row=1, column=0, sticky="nsew")
        left.grid_propagate(False)
        ctk.CTkLabel(left, text="VAULT", font=Fonts.body_bold, text_color=Colors.text_sub).pack(anchor="w", padx=16, pady=(16, 7))
        self.folders = ctk.CTkScrollableFrame(left, fg_color="transparent", height=145)
        self.folders.pack(fill="x", padx=8)
        ctk.CTkButton(left, text="+ Folder", height=28, fg_color="transparent", text_color=Colors.primary, anchor="w", command=self.new_folder).pack(fill="x", padx=12, pady=(5, 10))
        ctk.CTkLabel(left, text="NOTES", font=Fonts.body_bold, text_color=Colors.text_sub).pack(anchor="w", padx=16, pady=(5, 7))
        self.note_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.note_list.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        ctk.CTkButton(left, text="Import Markdown", height=30, command=self.import_markdown, fg_color="transparent", border_width=1, border_color=Colors.border, text_color=Colors.text).pack(fill="x", padx=12, pady=(0, 12))

        center = ctk.CTkFrame(self, fg_color=Colors.bg, corner_radius=0)
        center.grid(row=1, column=1, sticky="nsew")
        center.grid_rowconfigure(2, weight=1)
        center.grid_columnconfigure(0, weight=1)
        self.title = ctk.CTkEntry(center, placeholder_text="Untitled note", font=("Segoe UI", 22, "bold"), border_width=0, fg_color="transparent", text_color=Colors.text)
        self.title.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 5))
        self.title.bind("<KeyRelease>", self.queue_save)
        self.meta = ctk.CTkLabel(center, text="Markdown • local and encrypted", text_color=Colors.text_sub, font=("Segoe UI", 11))
        self.meta.grid(row=1, column=0, sticky="w", padx=26, pady=(0, 8))
        self.editor = ctk.CTkTextbox(center, wrap="word", font=("Cascadia Code", 13), fg_color=Colors.card, text_color=Colors.text, border_width=1, border_color=Colors.border)
        self.editor.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 18))
        self.editor.bind("<KeyRelease>", self.queue_save)

        right = ctk.CTkFrame(self, width=245, fg_color=Colors.card, corner_radius=0)
        right.grid(row=1, column=2, sticky="nsew")
        right.grid_propagate(False)
        self.side_title = ctk.CTkLabel(right, text="BACKLINKS", font=Fonts.body_bold, text_color=Colors.text_sub)
        self.side_title.pack(anchor="w", padx=16, pady=(16, 8))
        self.side = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.side.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.export_button = ctk.CTkButton(right, text="Export Markdown", height=30, command=self.export_markdown, fg_color="transparent", border_width=1, border_color=Colors.border, text_color=Colors.text)
        self.export_button.pack(fill="x", padx=12, pady=(0, 12))


    def update_view(self, context=None):
        if not context:
            return
        try:
            if self.vault:
                self.vault.close()
            self.vault = Vault(context["vault_name"], context["password"])
        except (KeyError, ValueError) as error:
            messagebox.showerror("Vault", str(error))
            self.controller.show_frame("WelcomeView")
            return
        self.note_id = None
        self.refresh_folders()
        self.refresh_notes()
        if self._notes:
            self.open_note(self._notes[0].id)
        else:
            self.new_note()

    def refresh_folders(self):
        for child in self.folders.winfo_children():
            child.destroy()
        ctk.CTkButton(self.folders, text="All notes", anchor="w", height=28, fg_color="transparent", text_color=Colors.text, command=lambda: self.select_folder(0)).pack(fill="x")
        for folder in self.vault.folders():
            ctk.CTkButton(self.folders, text=f"  {folder.name}", anchor="w", height=28, fg_color="transparent", text_color=Colors.text, command=lambda folder_id=folder.id: self.select_folder(folder_id)).pack(fill="x")

    def select_folder(self, folder_id):
        self.folder_id = folder_id
        self.refresh_notes()

    def refresh_notes(self):
        if not self.vault:
            return
        query = self.search.get().casefold() if hasattr(self, "search") else ""
        self._notes = [note for note in self.vault.notes() if (not self.folder_id or note.folder_id == self.folder_id) and (not query or query in note.title.casefold() or query in note.content.casefold())]
        for child in self.note_list.winfo_children():
            child.destroy()
        for note in self._notes:
            preview = note.content.replace("\n", " ").strip()[:45] or "Empty note"
            button = ctk.CTkButton(self.note_list, text=f"{note.title}\n{preview}", anchor="w", height=51, fg_color=Colors.input_bg if note.id == self.note_id else "transparent", hover_color=Colors.input_bg, text_color=Colors.text, command=lambda note_id=note.id: self.open_note(note_id))
            button.pack(fill="x", pady=1)

    def open_note(self, note_id):
        self.save()
        note = next((item for item in self.vault.notes() if item.id == note_id), None)
        if not note:
            return
        self.note_id = note.id
        self.folder_id = note.folder_id
        self.title.delete(0, "end")
        self.title.insert(0, note.title)
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", note.content)
        self.meta.configure(text=f"Markdown • updated {note.updated_at or 'now'}")
        self.refresh_notes()
        self.show_backlinks()

    def new_note(self):
        if not self.vault:
            return
        self.save()
        existing = {note.title.casefold() for note in self.vault.notes()}
        title, number = "Untitled", 1
        while title.casefold() in existing:
            number += 1
            title = f"Untitled {number}"
        self.vault.create_note(title, folder_id=self.folder_id)
        self.refresh_notes()
        self.open_note(next(note.id for note in self.vault.notes() if note.title == title))
        self.title.focus()
        self.title.select_range(0, "end")

    def new_folder(self):
        if not self.vault:
            return
        name = simpledialog.askstring("New folder", "Folder name:", parent=self)
        if name and name.strip():
            self.vault.create_folder(name.strip())
            self.refresh_folders()

    def queue_save(self, _event=None):
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save_job = self.after(650, self.save)

    def save(self, _event=None):
        if self._save_job:
            self.after_cancel(self._save_job)
            self._save_job = None
        if self.vault and self.note_id:
            title = self.title.get().strip() or "Untitled"
            self.vault.save_note(self.note_id, title, self.editor.get("1.0", "end-1c"), self.folder_id)
            self.meta.configure(text="Saved • Markdown • local and encrypted")
            self.refresh_notes()
            self.show_backlinks()
        return "break"

    def show_backlinks(self):
        self.side_title.configure(text="BACKLINKS")
        for child in self.side.winfo_children():
            child.destroy()
        if not self.vault or not self.note_id:
            return
        title = self.title.get().strip()
        links = self.vault.backlinks(title)
        if not links:
            ctk.CTkLabel(self.side, text="No linked mentions yet.\nUse [[Note title]] or [text](Note.md).", justify="left", wraplength=205, text_color=Colors.text_sub, font=Fonts.body).pack(anchor="w", padx=8, pady=8)
            return
        for note in links:
            ctk.CTkButton(self.side, text=note.title, anchor="w", fg_color="transparent", text_color=Colors.primary, command=lambda note_id=note.id: self.open_note(note_id)).pack(fill="x", pady=2)

    def show_graph(self):
        self.save()
        self.side_title.configure(text="VAULT GRAPH")
        for child in self.side.winfo_children():
            child.destroy()
        canvas = tk.Canvas(self.side, width=215, height=260, bg="#1F2937", highlightthickness=0)
        canvas.pack(fill="x", padx=5, pady=5)
        notes, edges = self.vault.graph()
        if not notes:
            return
        center_x, center_y, radius = 108, 130, max(42, min(92, 15 * len(notes)))
        positions = {}
        for index, note in enumerate(notes):
            angle = (2 * math.pi * index / len(notes)) - math.pi / 2
            positions[note.id] = (center_x + radius * math.cos(angle), center_y + radius * math.sin(angle))
        for source, target in edges:
            canvas.create_line(*positions[source], *positions[target], fill="#64748B", width=1)
        for note in notes:
            x, y = positions[note.id]
            canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#818CF8", outline="")
            canvas.create_text(x, y + 14, text=note.title[:15], fill="#E5E7EB", font=("Segoe UI", 7))
        ctk.CTkLabel(self.side, text=f"{len(notes)} notes • {len(edges)} links\nLinks are read from [[wiki links]] and Markdown links.", justify="left", wraplength=205, text_color=Colors.text_sub, font=Fonts.body).pack(anchor="w", padx=8, pady=8)

    def import_markdown(self):
        path = filedialog.askopenfilename(filetypes=[("Markdown", "*.md *.markdown"), ("Text", "*.txt")])
        if not path:
            return
        try:
            source = Path(path)
            self.vault.create_note(source.stem, source.read_text(encoding="utf-8"), self.folder_id)
            self.refresh_notes()
        except (OSError, UnicodeError) as error:
            messagebox.showerror("Import Markdown", str(error))

    def export_markdown(self):
        if not self.note_id:
            return
        self.save()
        title = self.title.get().strip() or "Untitled"
        path = filedialog.asksaveasfilename(defaultextension=".md", initialfile=f"{title}.md", filetypes=[("Markdown", "*.md")])
        if path:
            try:
                Path(path).write_text(self.editor.get("1.0", "end-1c"), encoding="utf-8")
            except OSError as error:
                messagebox.showerror("Export Markdown", str(error))
