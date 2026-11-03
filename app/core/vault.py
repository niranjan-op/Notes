"""Small UI-facing adapter over the encrypted C++ vault."""
from __future__ import annotations

import re
from dataclasses import dataclass

import secure_storage

from .config import vault_path


LINK_PATTERN = re.compile(r"\[\[([^\]#|]+)(?:#[^\]]+)?(?:\|[^\]]+)?\]\]|\[[^\]]*\]\(([^)#]+)(?:#[^)]+)?\)")


@dataclass(frozen=True)
class Note:
    id: int
    folder_id: int
    title: str
    content: str
    is_markdown: bool
    created_at: str
    updated_at: str


class Vault:
    def __init__(self, name: str, password: str):
        self.name = name
        self._db = secure_storage.DbOperations(str(vault_path(name)))
        if not self._db.connect(password, name):
            raise ValueError("Could not unlock vault")

    def close(self) -> None:
        self._db.close()

    def notes(self) -> list[Note]:
        return [Note(n.id, n.folder_id, n.title, n.content, n.is_markdown, n.created_at, n.updated_at)
                for n in self._db.get_all_notes()]

    def folders(self):
        return self._db.get_all_folders()

    def create_note(self, title: str, content: str = "", folder_id: int = 0) -> None:
        self._db.add_note(title, content, True, folder_id)

    def save_note(self, note_id: int, title: str, content: str, folder_id: int = 0) -> None:
        self._db.update_note(note_id, title, content, True, folder_id)

    def create_folder(self, name: str, parent_id: int = 0) -> None:
        self._db.add_folder(name, parent_id)

    @staticmethod
    def links(content: str) -> set[str]:
        links = set()
        for wiki, markdown in LINK_PATTERN.findall(content):
            target = (wiki or markdown).strip()
            if not target or "://" in target:
                continue
            links.add(target.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".md").strip())
        return links

    def backlinks(self, title: str) -> list[Note]:
        wanted = title.casefold()
        return [note for note in self.notes() if wanted in {link.casefold() for link in self.links(note.content)}]

    def graph(self) -> tuple[list[Note], list[tuple[int, int]]]:
        notes = self.notes()
        by_title = {note.title.casefold(): note.id for note in notes}
        edges = []
        for note in notes:
            for target in self.links(note.content):
                target_id = by_title.get(target.casefold())
                if target_id and target_id != note.id:
                    edges.append((note.id, target_id))
        return notes, edges
