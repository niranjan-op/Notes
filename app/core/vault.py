"""Small UI-facing adapter over the encrypted C++ vault."""
from __future__ import annotations

import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import secure_storage

from .config import vault_path


LINK_PATTERN = re.compile(r"\[\[([^\]#|]+)(?:#[^\]]+)?(?:\|[^\]]+)?\]\]|\[[^\]]*\]\(([^)#]+)(?:#[^)]+)?\)")
_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_FILENAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                       *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(name: str) -> str:
    """Return a cross-platform file or folder name for ``name``."""
    cleaned = _UNSAFE_FILENAME.sub("-", name).strip().rstrip(". ")[:120] or "Untitled"
    if cleaned.split(".")[0].upper() in _RESERVED_FILENAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def _unique(name: str, used: set[str], suffix: str = "") -> str:
    candidate, number = f"{name}{suffix}", 2
    while candidate.casefold() in used:
        candidate = f"{name} ({number}){suffix}"
        number += 1
    used.add(candidate.casefold())
    return candidate


@dataclass(frozen=True)
class Note:
    id: int
    folder_id: int
    title: str
    content: str
    is_markdown: bool
    created_at: str
    updated_at: str


class DuplicateNameError(ValueError):
    """Raised when a folder name already exists under the same parent."""


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

    def create_note(self, title: str, content: str = "", folder_id: int = 0) -> int:
        """Create a note and return its id."""
        self._db.add_note(title, content, True, folder_id)
        return max((note.note_id for note in self._db.get_all_mini_notes()), default=0)

    def save_note(self, note_id: int, title: str, content: str, folder_id: int = 0) -> None:
        self._db.update_note(note_id, title, content, True, folder_id)

    def delete_note(self, note_id: int) -> None:
        self._db.delete_note(note_id)

    def folder_name_exists(self, name: str, parent_id: int = 0, exclude_id: int | None = None) -> bool:
        """Return True when a sibling folder already uses ``name`` (case-insensitive)."""
        wanted = name.strip().casefold()
        return any(
            folder.parent_id == parent_id and folder.name.casefold() == wanted and folder.id != exclude_id
            for folder in self.folders()
        )

    def create_folder(self, name: str, parent_id: int = 0) -> int:
        """Create a folder and return its id.

        Raises ValueError for empty names and DuplicateNameError when a sibling
        folder already has the same name.
        """
        name = name.strip()
        if not name:
            raise ValueError("Enter a folder name.")
        if self.folder_name_exists(name, parent_id):
            raise DuplicateNameError(f"A folder named “{name}” already exists here.")
        self._db.add_folder(name, parent_id)
        return max((folder.id for folder in self.folders()), default=0)

    def descendant_folder_ids(self, folder_id: int) -> list[int]:
        """Return ``folder_id`` and every nested folder id, deepest first."""
        children: dict[int, list[int]] = {}
        for folder in self.folders():
            children.setdefault(folder.parent_id, []).append(folder.id)
        ordered, stack = [], [folder_id]
        while stack:
            current = stack.pop()
            ordered.append(current)
            stack.extend(children.get(current, []))
        return list(reversed(ordered))

    def delete_folder(self, folder_id: int) -> None:
        """Delete a folder, its sub-folders and every note inside them."""
        if folder_id == 0:
            raise ValueError("The vault root cannot be deleted.")
        for current in self.descendant_folder_ids(folder_id):
            self._db.delete_folder(current)

    def export_zip(self, destination: Path, folder_id: int = 0) -> int:
        """Write notes as Markdown files in a .zip that mirrors the folder tree.

        Exported files are NOT encrypted. The archive is written to a temporary
        file first and moved into place, so a failure never leaves a partial zip.
        Returns the number of notes exported.
        """
        destination = Path(destination)
        folders = {folder.id: folder for folder in self.folders()}
        if folder_id and folder_id not in folders:
            raise ValueError("That folder no longer exists.")
        children: dict[int, list] = {}
        for folder in folders.values():
            children.setdefault(folder.parent_id if folder.parent_id in folders else 0, []).append(folder)
        notes_by_folder: dict[int, list[Note]] = {}
        for note in self.notes():
            notes_by_folder.setdefault(note.folder_id if note.folder_id in folders else 0, []).append(note)

        root_name = safe_filename(folders[folder_id].name if folder_id else self.name)
        temporary = destination.with_name(destination.name + ".partial")
        exported = 0
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                def write_folder(current: int, path: str) -> None:
                    nonlocal exported
                    used: set[str] = set()
                    archive.writestr(zipfile.ZipInfo(path + "/"), "")
                    for folder in sorted(children.get(current, []), key=lambda item: item.name.casefold()):
                        write_folder(folder.id, f"{path}/{_unique(safe_filename(folder.name), used)}")
                    for note in sorted(notes_by_folder.get(current, []), key=lambda item: item.title.casefold()):
                        name = _unique(safe_filename(note.title), used, ".md")
                        archive.writestr(f"{path}/{name}", note.content.encode("utf-8"))
                        exported += 1

                write_folder(folder_id, root_name)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return exported

    def merge_database(self, source_path: Path, password: str) -> tuple[int, int]:
        """Merge a compatible Secure Notes SQLCipher database without modifying it.

        Folder names are reused only within the same parent.  Notes with identical
        folder, title and content are skipped, so a retry is safe after interruption.
        """
        source_path = Path(source_path)
        if source_path.suffix.lower() != ".db":
            raise ValueError("Choose a Secure Notes .db file.")

        source = secure_storage.DbOperations(str(source_path.parent))
        if not hasattr(source, "connect_readonly"):
            raise ValueError("This build of Secure Notes cannot merge vaults. Rebuild the storage extension.")
        if not source.connect_readonly(password, source_path.stem):
            raise ValueError("Could not unlock that database with this password.")
        try:
            source_folders = list(source.get_all_folders())
            source_notes = list(source.get_all_notes())
            folder_map = {0: 0}
            target_folders = self.folders()
            existing_folders = {
                (folder.parent_id, folder.name.casefold()): folder.id
                for folder in target_folders
            }
            pending = {folder.id: folder for folder in source_folders}
            while pending:
                progressed = False
                for old_id, folder in list(pending.items()):
                    if folder.parent_id not in folder_map:
                        continue
                    parent_id = folder_map[folder.parent_id]
                    key = (parent_id, folder.name.casefold())
                    if key not in existing_folders:
                        existing_folders[key] = self.create_folder(folder.name, parent_id)
                    folder_map[old_id] = existing_folders[key]
                    del pending[old_id]
                    progressed = True
                if not progressed:
                    raise ValueError("The source vault contains an invalid folder hierarchy.")

            existing_notes = {
                (note.folder_id, note.title, note.content)
                for note in self.notes()
            }
            imported = skipped = 0
            for note in source_notes:
                key = (folder_map.get(note.folder_id, 0), note.title, note.content)
                if key in existing_notes:
                    skipped += 1
                    continue
                self.create_note(note.title, note.content, key[0])
                existing_notes.add(key)
                imported += 1
            return imported, skipped
        finally:
            source.close()

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
