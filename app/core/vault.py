"""Small UI-facing adapter over the encrypted C++ vault."""
from __future__ import annotations

import base64
import binascii
from datetime import datetime
import hashlib
import os
import re
import shutil
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path

import secure_storage

from .config import get_vault_dir, is_filesystem_vault, vault_path


LINK_PATTERN = re.compile(
    r"(?<!\!)\[\[([^\]#|]+)(?:#[^\]]+)?(?:\|[^\]]+)?\]\]|(?<!\!)\[[^\]]*\]\(([^)#]+)(?:#[^)]+)?\)"
)
_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_FILENAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                       *(f"LPT{i}" for i in range(1, 10))}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _normalize_asset_key(target: str) -> str:
    cleaned = urllib.parse.unquote(target.strip()).replace("\\", "/")
    while cleaned.startswith("./") or cleaned.startswith("/"):
        cleaned = cleaned[2:] if cleaned.startswith("./") else cleaned[1:]
    return cleaned.casefold()


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


@dataclass(frozen=True)
class FolderItem:
    id: int
    name: str
    parent_id: int
    created_at: str = ""
    updated_at: str = ""


_IGNORED_FS_DIRS = {".git", ".obsidian", ".trash", "assets", "__pycache__"}


class DuplicateNameError(ValueError):
    """Raised when a folder name already exists under the same parent."""


class Vault:
    def __init__(self, name: str, password: str = ""):
        self.name = name
        self.is_encrypted = not is_filesystem_vault(name)
        self._attachment_cache: dict[str, bytes] | None = None
        self._attachment_paths: dict[str, str] = {}
        self._fs_folder_ids: dict[str, int] = {}
        self._fs_folder_paths: dict[int, Path] = {}
        self._fs_note_ids: dict[str, int] = {}
        self._fs_note_paths: dict[int, Path] = {}
        self._next_fid = 1
        self._next_nid = 1
        if self.is_encrypted:
            self.root_dir = vault_path(name)
            self._db = secure_storage.DbOperations(str(self.root_dir))
            if not self._db.connect(password, name):
                raise ValueError("Could not unlock vault")
        else:
            self._db = None
            self.root_dir = get_vault_dir(name)
            os.makedirs(self.root_dir / "assets", exist_ok=True)
            self._scan_filesystem()

    def close(self) -> None:
        if self._attachment_cache is not None:
            self._attachment_cache.clear()
            self._attachment_cache = None
        self._attachment_paths.clear()
        self._fs_folder_ids.clear()
        self._fs_folder_paths.clear()
        self._fs_note_ids.clear()
        self._fs_note_paths.clear()
        if self._db is not None:
            self._db.close()

    # ------------------------------------------------- filesystem mode helpers
    @staticmethod
    def _fmt_ts(ts: float) -> str:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

    def _rel_key(self, path: Path) -> str:
        return path.resolve().relative_to(self.root_dir.resolve()).as_posix().casefold()

    def _assign_folder_id(self, folder_path: Path) -> int:
        key = self._rel_key(folder_path)
        fid = self._fs_folder_ids.get(key)
        if fid is None:
            fid = self._next_fid
            self._next_fid += 1
            self._fs_folder_ids[key] = fid
        self._fs_folder_paths[fid] = folder_path
        return fid

    def _assign_note_id(self, file_path: Path) -> int:
        key = self._rel_key(file_path)
        nid = self._fs_note_ids.get(key)
        if nid is None:
            nid = self._next_nid
            self._next_nid += 1
            self._fs_note_ids[key] = nid
        self._fs_note_paths[nid] = file_path
        return nid

    def _scan_filesystem(self) -> tuple[list[FolderItem], list[Note]]:
        root = self.root_dir.resolve()
        if not root.exists():
            os.makedirs(root / "assets", exist_ok=True)
        folders_out: list[FolderItem] = []
        notes_out: list[Note] = []
        active_fids: dict[int, Path] = {}
        active_nids: dict[int, Path] = {}

        def walk_dir(current_dir: Path, parent_id: int) -> None:
            try:
                entries = sorted(current_dir.iterdir(), key=lambda p: p.name.casefold())
            except OSError:
                return
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    if parent_id == 0 and entry.name.casefold() in _IGNORED_FS_DIRS:
                        continue
                    fid = self._assign_folder_id(entry)
                    active_fids[fid] = entry
                    try:
                        st = entry.stat()
                        cts, uts = self._fmt_ts(st.st_ctime), self._fmt_ts(st.st_mtime)
                    except OSError:
                        cts = uts = ""
                    folders_out.append(FolderItem(fid, entry.name, parent_id, cts, uts))
                    walk_dir(entry, fid)
                elif entry.is_file() and entry.suffix.lower() in {".md", ".markdown"}:
                    nid = self._assign_note_id(entry)
                    active_nids[nid] = entry
                    try:
                        content = entry.read_text(encoding="utf-8")
                        st = entry.stat()
                        cts, uts = self._fmt_ts(st.st_ctime), self._fmt_ts(st.st_mtime)
                    except (OSError, UnicodeDecodeError):
                        continue
                    notes_out.append(Note(nid, parent_id, entry.stem, content, True, cts, uts))

        walk_dir(root, 0)
        self._fs_folder_paths = active_fids
        self._fs_note_paths = active_nids
        notes_out.sort(key=lambda n: (n.updated_at, n.id), reverse=True)
        return folders_out, notes_out

    def notes(self) -> list[Note]:
        if not self.is_encrypted:
            _, notes_out = self._scan_filesystem()
            return notes_out
        return [
            Note(n.id, n.folder_id, n.title, n.content, n.is_markdown, n.created_at, n.updated_at)
            for n in self._db.get_all_notes()
            if n.is_markdown
        ]

    def _ensure_attachments_loaded(self) -> dict[str, bytes]:
        if self._attachment_cache is not None:
            return self._attachment_cache
        cache: dict[str, bytes] = {}
        paths: dict[str, str] = {}
        if not self.is_encrypted:
            assets_dir = self.root_dir / "assets"
            if assets_dir.is_dir():
                for entry in sorted(assets_dir.iterdir(), key=lambda p: p.name.casefold()):
                    if not entry.is_file() or entry.suffix.lower() not in IMAGE_EXTENSIONS:
                        continue
                    try:
                        raw = entry.read_bytes()
                    except OSError:
                        continue
                    if not raw:
                        continue
                    canonical = f"assets/{entry.name}"
                    key = _normalize_asset_key(canonical)
                    base_key = _normalize_asset_key(entry.name)
                    cache[key] = raw
                    cache.setdefault(base_key, raw)
                    paths[key] = canonical
                    paths.setdefault(base_key, canonical)
                    digest = hashlib.sha256(raw).hexdigest()[:16]
                    paths.setdefault(f"sha256:{digest}{entry.suffix.lower()}", canonical)
            self._attachment_cache = cache
            self._attachment_paths = paths
            return cache

        for rec in self._db.get_all_notes():
            if rec.is_markdown or not rec.title or not rec.content:
                continue
            try:
                raw = base64.b64decode(rec.content, validate=False)
            except (binascii.Error, ValueError):
                continue
            if not raw:
                continue
            canonical = rec.title.replace("\\", "/").lstrip("/")
            key = _normalize_asset_key(canonical)
            base_key = _normalize_asset_key(canonical.rsplit("/", 1)[-1])
            cache[key] = raw
            cache.setdefault(base_key, raw)
            paths[key] = canonical
            paths.setdefault(base_key, canonical)
            digest = hashlib.sha256(raw).hexdigest()[:16]
            ext = Path(canonical).suffix.lower()
            paths.setdefault(f"sha256:{digest}{ext}", canonical)
        self._attachment_cache = cache
        self._attachment_paths = paths
        return cache

    def attachments(self) -> dict[str, bytes]:
        """Return a mapping of canonical attachment path -> raw bytes."""
        cache = self._ensure_attachments_loaded()
        result: dict[str, bytes] = {}
        for key, canonical in self._attachment_paths.items():
            if not key.startswith("sha256:") and key == _normalize_asset_key(canonical) and key in cache:
                result[canonical] = cache[key]
        return result

    def save_attachment(self, data: bytes, extension: str = ".png", name_hint: str = "pasted-image") -> str:
        """Store an image or GIF attachment in the vault and return its Markdown path."""
        if not data:
            raise ValueError("Attachment data is empty.")
        ext = (extension if extension.startswith(".") else f".{extension}").lower()
        if ext == ".jpeg":
            ext = ".jpg"
        if ext not in IMAGE_EXTENSIONS:
            ext = ".png"
        cache = self._ensure_attachments_loaded()
        digest = hashlib.sha256(data).hexdigest()[:16]
        dedup_key = f"sha256:{digest}{ext}"
        if dedup_key in self._attachment_paths:
            return self._attachment_paths[dedup_key]

        raw_stem = Path(name_hint).stem if name_hint else "pasted-image"
        stem = safe_filename(raw_stem)[:40].strip("-_ ") or "pasted-image"
        canonical = f"assets/{stem}-{digest[:10]}{ext}"
        if self.is_encrypted:
            b64 = base64.b64encode(data).decode("ascii")
            self._db.add_note(canonical, b64, False, -1)
        else:
            assets_dir = self.root_dir / "assets"
            os.makedirs(assets_dir, exist_ok=True)
            (self.root_dir / canonical).write_bytes(data)

        norm_key = _normalize_asset_key(canonical)
        base_key = _normalize_asset_key(canonical.rsplit("/", 1)[-1])
        cache[norm_key] = data
        cache[base_key] = data
        self._attachment_paths[norm_key] = canonical
        self._attachment_paths.setdefault(base_key, canonical)
        self._attachment_paths[dedup_key] = canonical
        return canonical

    def get_attachment(self, target: str) -> bytes | None:
        """Resolve an attachment path or inline data URI to raw image/GIF bytes."""
        if not target:
            return None
        stripped = target.strip()
        if stripped.startswith("data:image/") and ";base64," in stripped:
            _, b64_part = stripped.split(";base64,", 1)
            try:
                return base64.b64decode(b64_part, validate=False)
            except (binascii.Error, ValueError):
                return None
        cache = self._ensure_attachments_loaded()
        key = _normalize_asset_key(stripped)
        if key in cache:
            return cache[key]
        base_key = _normalize_asset_key(stripped.rsplit("/", 1)[-1])
        if base_key in cache:
            return cache[base_key]
        if not self.is_encrypted:
            clean_rel = urllib.parse.unquote(stripped).replace("\\", "/").lstrip("/")
            root_resolved = self.root_dir.resolve()
            for candidate in (root_resolved / clean_rel, root_resolved / "assets" / Path(clean_rel).name):
                try:
                    resolved = candidate.resolve()
                    resolved.relative_to(root_resolved)
                    if resolved.is_file():
                        raw = resolved.read_bytes()
                        cache[key] = raw
                        return raw
                except (OSError, ValueError):
                    continue
        return None

    def folders(self):
        if not self.is_encrypted:
            folders_out, _ = self._scan_filesystem()
            return folders_out
        return self._db.get_all_folders()

    def create_note(self, title: str, content: str = "", folder_id: int = 0) -> int:
        """Create a note and return its id."""
        if not self.is_encrypted:
            self._scan_filesystem()
            folder_dir = self._fs_folder_paths.get(folder_id, self.root_dir)
            os.makedirs(folder_dir, exist_ok=True)
            base_stem = safe_filename(title)
            candidate = folder_dir / f"{base_stem}.md"
            n = 2
            while candidate.exists():
                candidate = folder_dir / f"{base_stem} ({n}).md"
                n += 1
            candidate.write_text(content, encoding="utf-8")
            return self._assign_note_id(candidate)
        self._db.add_note(title, content, True, folder_id)
        return max((note.note_id for note in self._db.get_all_mini_notes()), default=0)

    def save_note(self, note_id: int, title: str, content: str, folder_id: int = 0) -> None:
        if not self.is_encrypted:
            old_path = self._fs_note_paths.get(note_id)
            folder_dir = self._fs_folder_paths.get(folder_id, self.root_dir)
            os.makedirs(folder_dir, exist_ok=True)
            base_stem = safe_filename(title)
            desired = folder_dir / f"{base_stem}.md"
            if old_path is not None and old_path.exists():
                same_file = desired.resolve() == old_path.resolve()
                if not same_file and desired.exists():
                    n = 2
                    while desired.exists() and desired.resolve() != old_path.resolve():
                        desired = folder_dir / f"{base_stem} ({n}).md"
                        n += 1
                if same_file and old_path.name != desired.name:
                    old_path = old_path.rename(desired)
                elif not same_file:
                    old_key = self._rel_key(old_path)
                    self._fs_note_ids.pop(old_key, None)
                    desired.write_text(content, encoding="utf-8")
                    try:
                        old_path.unlink()
                    except OSError:
                        pass
                    self._fs_note_ids[self._rel_key(desired)] = note_id
                    self._fs_note_paths[note_id] = desired
                    return
            elif desired.exists():
                n = 2
                while desired.exists():
                    desired = folder_dir / f"{base_stem} ({n}).md"
                    n += 1
            desired.write_text(content, encoding="utf-8")
            self._fs_note_ids[self._rel_key(desired)] = note_id
            self._fs_note_paths[note_id] = desired
            return
        self._db.update_note(note_id, title, content, True, folder_id)

    def delete_note(self, note_id: int) -> None:
        if not self.is_encrypted:
            old_path = self._fs_note_paths.pop(note_id, None)
            if old_path is not None:
                self._fs_note_ids.pop(self._rel_key(old_path), None)
                try:
                    old_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return
        self._db.delete_note(note_id)

    def folder_name_exists(self, name: str, parent_id: int = 0, exclude_id: int | None = None) -> bool:
        """Return True when a sibling folder already uses ``name`` (case-insensitive)."""
        wanted = name.strip().casefold()
        if not self.is_encrypted and parent_id == 0 and wanted in _IGNORED_FS_DIRS:
            return True
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
        if not self.is_encrypted:
            self._scan_filesystem()
            parent_dir = self._fs_folder_paths.get(parent_id, self.root_dir)
            new_dir = parent_dir / safe_filename(name)
            os.makedirs(new_dir, exist_ok=True)
            return self._assign_folder_id(new_dir)
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
        if not self.is_encrypted:
            self._scan_filesystem()
            target_dir = self._fs_folder_paths.get(folder_id)
            if target_dir is not None and target_dir.exists():
                root_resolved = self.root_dir.resolve()
                resolved = target_dir.resolve()
                resolved.relative_to(root_resolved)
                if resolved != root_resolved:
                    shutil.rmtree(resolved)
            self._scan_filesystem()
            return
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
                for rel_path, raw_bytes in sorted(self.attachments().items()):
                    clean_rel = rel_path.replace("\\", "/").lstrip("/")
                    archive.writestr(f"{root_name}/{clean_rel}", raw_bytes)
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
            existing_assets = {_normalize_asset_key(path) for path in self.attachments()}
            imported = skipped = 0
            for note in source_notes:
                if not note.is_markdown:
                    norm_title = _normalize_asset_key(note.title)
                    if norm_title and norm_title not in existing_assets and note.content:
                        if self.is_encrypted:
                            self._db.add_note(note.title, note.content, False, -1)
                        else:
                            try:
                                raw = base64.b64decode(note.content, validate=False)
                                assets_dir = self.root_dir / "assets"
                                os.makedirs(assets_dir, exist_ok=True)
                                (assets_dir / safe_filename(Path(note.title).name)).write_bytes(raw)
                            except (binascii.Error, OSError, ValueError):
                                pass
                        existing_assets.add(norm_title)
                        self._attachment_cache = None
                    continue
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
        if "[[" not in content and "](" not in content:
            return set()
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
