import gc
import tempfile
import unittest
import zipfile
from pathlib import Path

import secure_storage

import app.core.config as cf
from app.core.markdown import (
    analyze,
    next_list_prefix,
    parse_inline,
    plain_text,
    split_table_row,
    table_alignments,
)
from app.core.updater import is_newer_version, parse_version, release_from_payload
from app.core.vault import DuplicateNameError, Vault


class VaultTests(unittest.TestCase):
    def test_links_support_wiki_and_markdown_forms(self):
        self.assertEqual(
            Vault.links("[[Project#Plan]] [Label](notes/Reference.md) [web](https://example.com)"),
            {"Project", "Reference"},
        )

    def test_native_storage_returns_markdown_content(self):
        with tempfile.TemporaryDirectory() as directory:
            database = secure_storage.DbOperations(directory)
            self.assertTrue(database.connect("test-password", "test-vault"))
            database.add_note("First", "[[Second]]", True)
            note = database.get_all_notes()[0]
            self.assertEqual((note.title, note.content, note.is_markdown), ("First", "[[Second]]", True))
            database.close()
            del database
            gc.collect()


class VaultFolderAndDeletionTests(unittest.TestCase):
    """Exercises real encrypted storage inside an isolated LOCALAPPDATA."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._original_base = cf.base_path
        cf.base_path = self._tmp.name
        cf.update_config("alpha")
        self.assertTrue(cf.create_db("password-1", "alpha"))
        gc.collect()
        self.vault = Vault("alpha", "password-1")

    def tearDown(self):
        if self.vault:
            self.vault.close()
        self.vault = None
        gc.collect()
        cf.base_path = self._original_base
        self._tmp.cleanup()

    def test_duplicate_folder_names_are_rejected_per_parent(self):
        docs = self.vault.create_folder("Docs")
        with self.assertRaises(DuplicateNameError):
            self.vault.create_folder("  docs ")
        nested = self.vault.create_folder("Docs", docs)  # same name, different parent is fine
        self.assertNotEqual(docs, nested)
        self.assertTrue(self.vault.folder_name_exists("DOCS", 0))
        with self.assertRaises(ValueError):
            self.vault.create_folder("   ")

    def test_create_note_returns_new_id(self):
        first = self.vault.create_note("One")
        second = self.vault.create_note("Two")
        self.assertGreater(second, first)
        self.assertEqual({n.id for n in self.vault.notes()}, {first, second})

    def test_delete_folder_removes_nested_folders_and_notes(self):
        top = self.vault.create_folder("Top")
        child = self.vault.create_folder("Child", top)
        grandchild = self.vault.create_folder("Grandchild", child)
        keep = self.vault.create_note("Keep")
        self.vault.create_note("A", folder_id=top)
        self.vault.create_note("B", folder_id=grandchild)
        self.vault.delete_folder(top)
        self.assertEqual(list(self.vault.folders()), [])
        self.assertEqual([n.id for n in self.vault.notes()], [keep])

    def test_delete_vault_removes_files_and_config_entry(self):
        self.vault.create_note("Secret")
        self.vault.close()
        self.vault = None
        gc.collect()
        cf.update_config("beta")
        cf.delete_vault("alpha")
        self.assertFalse(cf.vault_path("alpha").exists())
        vaults, last_open = cf.read_config()
        self.assertEqual(vaults, ["beta"])
        self.assertEqual(last_open, "beta")

    def test_delete_vault_rejects_path_traversal(self):
        for name in ("..", "../alpha", "a/b", ""):
            with self.assertRaises(ValueError):
                cf.delete_vault(name)
        self.assertTrue(Path(cf.vault_path("alpha")).exists())

    def test_vault_name_validation(self):
        self.assertIsNone(cf.validate_vault_name("Personal"))
        self.assertIsNotNone(cf.validate_vault_name("CON"))
        self.assertIsNotNone(cf.validate_vault_name("bad:name"))

    def test_preferences_round_trip(self):
        cf.set_preference("theme", "light")
        self.assertEqual(cf.get_preference("theme"), "light")
        self.assertEqual(cf.read_config()[0], ["alpha"])

    def test_export_zip_preserves_hierarchy_and_deduplicates_filenames(self):
        eng = self.vault.create_folder("Engineering")
        sub = self.vault.create_folder("API:Specs", eng)
        self.vault.create_note("Overview", "# Overview", 0)
        self.vault.create_note("Endpoints", "GET /v1", sub)
        self.vault.create_note("Endpoints", "POST /v1", sub)  # duplicate title in same folder
        dest = Path(self._tmp.name) / "export.zip"
        count = self.vault.export_zip(dest)
        self.assertEqual(count, 3)
        with zipfile.ZipFile(dest, "r") as zf:
            names = set(zf.namelist())
            self.assertIn("alpha/Overview.md", names)
            self.assertIn("alpha/Engineering/API-Specs/Endpoints.md", names)
            self.assertIn("alpha/Engineering/API-Specs/Endpoints (2).md", names)
            self.assertEqual(zf.read("alpha/Overview.md").decode("utf-8"), "# Overview")


class MarkdownAnalysisTests(unittest.TestCase):
    def test_heading_markers_and_inline_tokens(self):
        doc = "# Hello **World** and [[Target|Alias]]\nParagraph with `code` and ==mark==."
        infos = analyze(doc)
        self.assertEqual(infos[0].kind, "heading")
        self.assertEqual(infos[0].level, 1)
        self.assertEqual(infos[0].marker_end, 2)  # "# "
        tokens = parse_inline(doc.splitlines()[0], base=0)
        kinds = [t.kind for t in tokens]
        self.assertEqual(kinds, ["bold", "wikilink"])
        self.assertEqual(tokens[0].markers, [(8, 10), (15, 17)])
        self.assertEqual(tokens[1].target, "Target")
        self.assertEqual(plain_text("Hello **World** [[Target|Alias]]"), "Hello World Alias")

    def test_table_and_code_fence_blocks(self):
        doc = (
            "| Name | Score |\n"
            "| :--- | ---: |\n"
            "| Alice | 95 |\n\n"
            "```python\n"
            "# Not a heading\n"
            "```\n"
        )
        infos = analyze(doc)
        self.assertEqual(
            [i.kind for i in infos],
            ["table_header", "table_separator", "table_row", "blank", "fence", "code", "fence", "blank"],
        )
        self.assertEqual(table_alignments("| :--- | :---: | ---: |"), ["left", "center", "right"])
        cells = split_table_row("| Alice | 95 |")
        self.assertEqual(["| Alice | 95 |"[s:e] for s, e in cells], ["Alice", "95"])

    def test_list_and_task_continuation(self):
        self.assertEqual(next_list_prefix("- [ ] Buy milk"), ("- [ ] ", False))
        self.assertEqual(next_list_prefix("1. First"), ("2. ", False))
        self.assertEqual(next_list_prefix("- "), ("- ", True))

    def test_large_document_analysis_stays_fast(self):
        block = "# Section\nParagraph with **bold**, *italic*, `code` and [[Link|Alias]].\n- [ ] Task item\n\n"
        large_doc = block * 500
        infos = analyze(large_doc)
        self.assertEqual(len(infos), 2001)
        self.assertEqual(infos[0].kind, "heading")
        self.assertEqual(infos[1].kind, "paragraph")
        self.assertEqual(infos[2].kind, "list")
        self.assertEqual(infos[2].task, " ")


class UpdaterTests(unittest.TestCase):
    def test_version_comparison(self):
        self.assertEqual(parse_version("v1.3.0"), (1, 3, 0))
        self.assertTrue(is_newer_version("v1.4.0", "1.3.0"))
        self.assertTrue(is_newer_version("1.3.1", "1.3.0"))
        self.assertFalse(is_newer_version("v1.3.0", "1.3.0"))
        self.assertFalse(is_newer_version("v1.2.9", "1.3.0"))

    def test_release_payload_extracts_trusted_windows_installer(self):
        payload = {
            "tag_name": "v1.4.0",
            "draft": False,
            "prerelease": False,
            "html_url": "https://github.com/niranjan-op/Notes/releases/tag/v1.4.0",
            "assets": [
                {
                    "name": "NotesApp-windows-x64.zip",
                    "browser_download_url": "https://github.com/niranjan-op/Notes/releases/download/v1.4.0/NotesApp-windows-x64.zip",
                    "size": 12000,
                },
                {
                    "name": "SecureNotes-Setup-1.4.0-x64.exe",
                    "browser_download_url": "https://github.com/niranjan-op/Notes/releases/download/v1.4.0/SecureNotes-Setup-1.4.0-x64.exe",
                    "size": 45000000,
                },
            ],
        }
        info = release_from_payload(payload, "1.3.0")
        self.assertIsNotNone(info)
        self.assertEqual(info.version, "1.4.0")
        self.assertEqual(info.installer_name, "SecureNotes-Setup-1.4.0-x64.exe")
        self.assertIsNone(release_from_payload(payload, "1.4.0"))


class ThemeTests(unittest.TestCase):
    def tearDown(self):
        import customtkinter as ctk
        from app.UI.styles import apply_color_theme
        apply_color_theme("default")
        ctk.set_appearance_mode("dark")

    def test_default_and_monochrome_themes_with_independent_light_dark_toggle(self):
        import customtkinter as ctk
        from app.UI.brand import _TONES, logo_image
        from app.UI.styles import Colors, _DEFAULT_PALETTE, apply_color_theme, current_color_theme, resolve

        logo = logo_image(22)

        # 1. Default theme (built-in indigo palette) with Light and Dark toggle
        self.assertEqual(apply_color_theme("Default"), "default")
        self.assertEqual(current_color_theme(), "default")
        ctk.set_appearance_mode("light")
        self.assertEqual(resolve(Colors.bg), "#FFFFFF")
        self.assertEqual(resolve(Colors.primary), "#4F46E5")
        ctk.set_appearance_mode("dark")
        self.assertEqual(resolve(Colors.bg), "#161618")
        self.assertEqual(resolve(Colors.primary), "#6366F1")
        default_logo_light = logo.cget("light_image")

        # 2. Monochrome theme (black & white) with independent Light and Dark toggle
        self.assertEqual(apply_color_theme("Monochrome"), "monochrome")
        self.assertEqual(current_color_theme(), "monochrome")

        for name in _DEFAULT_PALETTE:
            pair = getattr(Colors, name)
            self.assertEqual(len(pair), 2, name)
            for hex_val in pair:
                r, g, b = hex_val[1:3], hex_val[3:5], hex_val[5:7]
                self.assertTrue(r == g == b, f"{name} ({hex_val}) is not pure black/white/grayscale")

        for tone_name, pair in _TONES.items():
            for hex_val in pair:
                r, g, b = hex_val[1:3], hex_val[3:5], hex_val[5:7]
                self.assertTrue(r == g == b, f"Icon tone {tone_name} ({hex_val}) is not monochrome")

        # Light mode in Monochrome
        ctk.set_appearance_mode("light")
        self.assertEqual(resolve(Colors.bg), "#FFFFFF")
        self.assertEqual(resolve(Colors.text), "#000000")
        self.assertEqual(resolve(Colors.primary), "#000000")
        self.assertEqual(resolve(Colors.on_primary), "#FFFFFF")
        self.assertEqual(current_color_theme(), "monochrome")

        # Dark mode in Monochrome
        ctk.set_appearance_mode("dark")
        self.assertEqual(resolve(Colors.bg), "#000000")
        self.assertEqual(resolve(Colors.text), "#FFFFFF")
        self.assertEqual(resolve(Colors.primary), "#FFFFFF")
        self.assertEqual(resolve(Colors.on_primary), "#000000")
        self.assertEqual(current_color_theme(), "monochrome")
        self.assertIsNot(logo.cget("light_image"), default_logo_light)
        self.assertIsNot(logo.cget("light_image"), logo.cget("dark_image"))


if __name__ == "__main__":
    unittest.main()
