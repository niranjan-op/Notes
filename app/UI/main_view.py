import math
import re
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

        bar = ctk.CTkFrame(self, fg_color=Colors.card, corner_radius=0, height=52)
        bar.grid(row=0, column=0, columnspan=3, sticky="ew")
        bar.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(bar, text="◈  Notes", font=("Segoe UI", 16, "bold"), text_color=Colors.text).grid(row=0, column=0, padx=18, pady=12)
        ctk.CTkButton(bar, text="+ Note", width=76, height=30, command=self.new_note, fg_color=Colors.primary, hover_color=Colors.primary_hover).grid(row=0, column=1, padx=(0, 8), pady=8)
        self.search = ctk.CTkEntry(bar, placeholder_text="Search notes", width=220, height=30)
        self.search.grid(row=0, column=2, sticky="e", padx=8, pady=8)
        self.search.bind("<KeyRelease>", lambda _event: self.refresh_notes())
        ctk.CTkButton(bar, text="Graph view", width=92, height=30, fg_color="transparent", border_width=1, border_color=Colors.border, text_color=Colors.text, command=self.show_graph).grid(row=0, column=3, padx=8, pady=8)
        ctk.CTkButton(bar, text="Settings", width=76, height=30, fg_color="transparent", text_color=Colors.text_sub, command=self.show_settings).grid(row=0, column=4, padx=(0, 12), pady=8)

        left = ctk.CTkFrame(self, width=235, fg_color=Colors.card, corner_radius=0)
        left.grid(row=1, column=0, sticky="nsew")
        left.grid_propagate(False)
        ctk.CTkLabel(left, text="Your vault", font=("Segoe UI", 15, "bold"), text_color=Colors.text).pack(anchor="w", padx=16, pady=(16, 7))
        ctk.CTkButton(left, text="＋  New folder", height=30, fg_color="transparent", text_color=Colors.primary, anchor="w", command=self.new_folder).pack(fill="x", padx=10, pady=(0, 6))
        self.folders = ctk.CTkScrollableFrame(left, fg_color="transparent", height=150)
        self.folders.pack(fill="x", padx=8)
        ctk.CTkLabel(left, text="Notes", font=("Segoe UI", 13, "bold"), text_color=Colors.text_sub).pack(anchor="w", padx=16, pady=(8, 7))
        self.note_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.note_list.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        center = ctk.CTkFrame(self, fg_color=Colors.bg, corner_radius=0)
        center.grid(row=1, column=1, sticky="nsew")
        center.grid_rowconfigure(2, weight=1)
        center.grid_columnconfigure(0, weight=1, uniform="editor")
        center.grid_columnconfigure(1, weight=1, uniform="editor")
        self.title = ctk.CTkEntry(center, placeholder_text="Untitled note", font=("Segoe UI", 22, "bold"), border_width=0, fg_color="transparent", text_color=Colors.text)
        self.title.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 5))
        self.title.bind("<KeyRelease>", self.queue_save)
        ctk.CTkButton(center, text="Delete note", width=92, height=28, fg_color="transparent", text_color="#D97985", command=self.delete_current_note).grid(row=0, column=1, sticky="e", padx=(0, 22), pady=(18, 5))
        self.meta = ctk.CTkLabel(center, text="Markdown source", text_color=Colors.text_sub, font=("Segoe UI", 11))
        self.meta.grid(row=1, column=0, sticky="w", padx=26, pady=(0, 8))
        ctk.CTkLabel(center, text="Live preview", text_color=Colors.text_sub, font=("Segoe UI", 11)).grid(row=1, column=1, sticky="w", padx=14, pady=(0, 8))
        self.editor = ctk.CTkTextbox(center, wrap="word", font=("Cascadia Code", 13), fg_color=Colors.card, text_color=Colors.text, border_width=1, border_color=Colors.border)
        self.editor.grid(row=2, column=0, sticky="nsew", padx=(20, 8), pady=(0, 18))
        self.preview = tk.Text(center, wrap="word", font=("Segoe UI", 14), padx=18, pady=18, relief="flat", borderwidth=0, state="disabled", background="#202938", foreground="#E7ECF4", insertbackground="#E7ECF4")
        self.preview.grid(row=2, column=1, sticky="nsew", padx=(8, 20), pady=(0, 18))
        self.preview.tag_configure("h1", font=("Segoe UI", 26, "bold"), spacing3=14, foreground="#F5F7FB")
        self.preview.tag_configure("h2", font=("Segoe UI", 21, "bold"), spacing3=12, foreground="#F5F7FB")
        self.preview.tag_configure("h3", font=("Segoe UI", 17, "bold"), spacing3=10, foreground="#F5F7FB")
        self.preview.tag_configure("bold", font=("Segoe UI", 14, "bold"))
        self.preview.tag_configure("code", font=("Cascadia Code", 12), background="#303B4D", foreground="#A5D6C8")
        self.preview.tag_configure("muted", foreground="#A8B3C5")
        self.editor.bind("<KeyRelease>", self.queue_save)
        self.editor.bind("<KeyRelease>", self.render_preview, add="+")

        right = ctk.CTkFrame(self, width=245, fg_color=Colors.card, corner_radius=0)
        right.grid(row=1, column=2, sticky="nsew")
        right.grid_propagate(False)
        self.side_title = ctk.CTkLabel(right, text="BACKLINKS", font=Fonts.body_bold, text_color=Colors.text_sub)
        self.side_title.pack(anchor="w", padx=16, pady=(16, 8))
        self.side = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.side.pack(fill="both", expand=True, padx=8, pady=(0, 8))


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
            self.vault.create_note("Welcome to your vault", "# Your notes, connected\n\nWrite in Markdown on the left. The preview updates as you type.\n\n- Create a note with **+ Note**\n- Link notes with [[wiki links]]\n- Open Graph view to explore connections\n- Create folders from the vault sidebar", self.folder_id)
            self.refresh_notes()
            self.open_note(self.vault.notes()[0].id)

    def refresh_folders(self):
        for child in self.folders.winfo_children():
            child.destroy()
        ctk.CTkButton(self.folders, text="▦  All notes", anchor="w", height=30, fg_color="transparent", text_color=Colors.text, command=lambda: self.select_folder(0)).pack(fill="x")
        folders = self.vault.folders()
        children = {}
        for folder in folders:
            children.setdefault(folder.parent_id, []).append(folder)

        def add_folder(folder, depth=0):
            ctk.CTkButton(self.folders, text=f"{'    ' * depth}▸  {folder.name}", anchor="w", height=28, fg_color=Colors.input_bg if folder.id == self.folder_id else "transparent", text_color=Colors.text, command=lambda folder_id=folder.id: self.select_folder(folder_id)).pack(fill="x")
            for child in children.get(folder.id, []):
                add_folder(child, depth + 1)

        for folder in children.get(0, []):
            add_folder(folder)

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
        self.render_preview()
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
            self.vault.create_folder(name.strip(), self.folder_id)
            self.refresh_folders()

    def delete_current_note(self):
        if not self.note_id or not messagebox.askyesno("Delete note", "Delete this note permanently?", parent=self):
            return
        self.vault.delete_note(self.note_id)
        self.note_id = None
        self.refresh_notes()
        self.title.delete(0, "end")
        self.editor.delete("1.0", "end")
        self.render_preview()
        if self._notes:
            self.open_note(self._notes[0].id)
        else:
            self.new_note()

    def show_settings(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Settings")
        dialog.geometry("430x390")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="Settings", font=("Segoe UI", 22, "bold"), text_color=Colors.text).pack(anchor="w", padx=24, pady=(22, 8))
        ctk.CTkLabel(dialog, text="Appearance", text_color=Colors.text_sub).pack(anchor="w", padx=24, pady=(12, 4))
        theme = ctk.CTkOptionMenu(dialog, values=["Dark", "Light", "System"], command=lambda value: ctk.set_appearance_mode(value.lower()))
        theme.set("Dark")
        theme.pack(fill="x", padx=24)
        ctk.CTkButton(dialog, text="Import Markdown note", command=self.import_markdown).pack(fill="x", padx=24, pady=(24, 8))
        ctk.CTkButton(dialog, text="Delete current note", fg_color="#9E3D4C", hover_color="#7C2E3B", command=lambda: (dialog.destroy(), self.delete_current_note())).pack(fill="x", padx=24, pady=8)
        ctk.CTkLabel(dialog, text="Vaults are encrypted. A forgotten master password cannot be reset or recovered. Keep a separate backup of your password. Without it, create a new vault and restore from a Markdown backup.", wraplength=370, justify="left", text_color=Colors.text_sub).pack(anchor="w", padx=24, pady=16)

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
        return "break"

    def render_preview(self, _event=None):
        raw = self.editor.get("1.0", "end-1c")
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        for line in raw.splitlines():
            heading = re.match(r"^(#{1,3})\s+(.*)$", line)
            if heading:
                self.preview.insert("end", heading.group(2) + "\n", f"h{len(heading.group(1))}")
                continue
            if not line.strip():
                self.preview.insert("end", "\n")
                continue
            cursor = 0
            for match in re.finditer(r"\*\*(.+?)\*\*|`([^`]+)`", line):
                self.preview.insert("end", line[cursor:match.start()])
                text = match.group(1) or match.group(2)
                self.preview.insert("end", text, "bold" if match.group(1) else "code")
                cursor = match.end()
            self.preview.insert("end", line[cursor:] + "\n")
        if not raw:
            self.preview.insert("end", "Your note preview appears here as you type.", "muted")
        self.preview.configure(state="disabled")

    def show_backlinks(self):
        self.side_title.configure(text="BACKLINKS")
        for child in self.side.winfo_children():
            child.destroy()
        if not self.vault or not self.note_id:
            return
        title = self.title.get().strip()
        links = self.vault.backlinks(title)
        if not links:
            empty = ctk.CTkFrame(self.side, fg_color=Colors.input_bg, corner_radius=8)
            empty.pack(fill="x", padx=8, pady=8)
            ctk.CTkLabel(empty, text="No backlinks", text_color=Colors.text, font=Fonts.body_bold).pack(anchor="w", padx=12, pady=(12, 4))
            ctk.CTkLabel(empty, text="Link another note with [[Note title]].", justify="left", wraplength=185, text_color=Colors.text_sub, font=Fonts.body).pack(anchor="w", padx=12, pady=(0, 12))
            return
        for note in links:
            ctk.CTkButton(self.side, text=note.title, anchor="w", fg_color="transparent", text_color=Colors.primary, command=lambda note_id=note.id: self.open_note(note_id)).pack(fill="x", pady=2)

    def show_graph(self):
        self.save()
        notes, edges = self.vault.graph()
        window = ctk.CTkToplevel(self)
        window.title("Vault graph")
        window.geometry("1000x720")
        window.minsize(650, 480)
        window.grid_rowconfigure(1, weight=1)
        window.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(window, fg_color=Colors.card, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(header, text="Vault graph", font=("Segoe UI", 18, "bold"), text_color=Colors.text).pack(side="left", padx=18, pady=12)
        ctk.CTkLabel(header, text="Scroll to zoom · drag to pan · click a note to open", text_color=Colors.text_sub).pack(side="left", padx=12)
        canvas = tk.Canvas(window, bg="#141B27", highlightthickness=0)
        canvas.grid(row=1, column=0, sticky="nsew")
        if not notes:
            canvas.create_text(400, 280, text="Create notes and link them with [[wiki links]]", fill="#A8B3C5", font=("Segoe UI", 16))
            return
        center_x, center_y, radius = 500, 350, max(100, min(300, 24 * len(notes)))
        positions = {}
        for index, note in enumerate(notes):
            angle = (2 * math.pi * index / len(notes)) - math.pi / 2
            positions[note.id] = (center_x + radius * math.cos(angle), center_y + radius * math.sin(angle))
        for source, target in edges:
            canvas.create_line(*positions[source], *positions[target], fill="#46556A", width=1.5)
        for note in notes:
            x, y = positions[note.id]
            tag = f"note-{note.id}"
            size = min(16, 9 + sum(note.id in edge for edge in edges))
            canvas.create_oval(x-size, y-size, x+size, y+size, fill="#80CDB2", outline="#C2F0DE", width=2, tags=(tag,))
            canvas.create_text(x, y+size+15, text=note.title, fill="#E4EAF2", font=("Segoe UI", 10), tags=(tag,))
            canvas.tag_bind(tag, "<Enter>", lambda _event, item=tag: canvas.itemconfigure(item, fill="#B8F2D7"))
            canvas.tag_bind(tag, "<Leave>", lambda _event, item=tag: canvas.itemconfigure(item, fill="#80CDB2"))
            canvas.tag_bind(tag, "<Button-1>", lambda _event, note_id=note.id: (window.destroy(), self.open_note(note_id)))
        canvas.bind("<MouseWheel>", lambda event: canvas.scale("all", event.x, event.y, 1.1 if event.delta > 0 else 0.9, 1.1 if event.delta > 0 else 0.9))
        canvas.bind("<ButtonPress-2>", lambda event: canvas.scan_mark(event.x, event.y))
        canvas.bind("<B2-Motion>", lambda event: canvas.scan_dragto(event.x, event.y, gain=1))
        ctk.CTkButton(header, text="−", width=34, command=lambda: canvas.scale("all", 500, 350, .9, .9)).pack(side="right", padx=(4, 12))
        ctk.CTkButton(header, text="+", width=34, command=lambda: canvas.scale("all", 500, 350, 1.1, 1.1)).pack(side="right", padx=4)

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

