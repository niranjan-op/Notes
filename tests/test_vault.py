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

    def test_encrypted_image_and_gif_attachments_persist_export_and_merge(self):
        import io
        from PIL import Image

        # Create a 2-frame animated GIF and a PNG in memory
        gif_buf = io.BytesIO()
        f1 = Image.new("RGBA", (32, 24), (255, 0, 0, 255))
        f2 = Image.new("RGBA", (32, 24), (0, 200, 80, 255))
        f1.save(gif_buf, format="GIF", save_all=True, append_images=[f2], duration=90, loop=0)
        gif_bytes = gif_buf.getvalue()

        png_buf = io.BytesIO()
        Image.new("RGBA", (48, 36), (40, 80, 220, 255)).save(png_buf, format="PNG")
        png_bytes = png_buf.getvalue()

        gif_path = self.vault.save_attachment(gif_bytes, ".gif", "demo-anim")
        png_path = self.vault.save_attachment(png_bytes, ".png", "screenshot")
        # Deduplication: saving identical bytes returns the same path
        self.assertEqual(self.vault.save_attachment(gif_bytes, ".gif", "other-name"), gif_path)
        self.assertTrue(gif_path.startswith("assets/") and gif_path.endswith(".gif"))
        self.assertTrue(png_path.startswith("assets/") and png_path.endswith(".png"))

        note_id = self.vault.create_note("Media Note", f"![anim]({gif_path})\n![shot]({png_path})")
        # Attachments must never appear as user notes
        self.assertEqual([n.id for n in self.vault.notes()], [note_id])
        self.assertEqual(self.vault.get_attachment(gif_path), gif_bytes)
        self.assertEqual(self.vault.get_attachment(Path(gif_path).name), gif_bytes)
        self.assertEqual(self.vault.get_attachment(png_path), png_bytes)

        # Reopen the encrypted vault from disk and verify attachments survive
        self.vault.close()
        self.vault = Vault("alpha", "password-1")
        self.assertEqual(self.vault.get_attachment(gif_path), gif_bytes)
        self.assertEqual(self.vault.get_attachment(png_path), png_bytes)
        self.assertEqual([n.title for n in self.vault.notes()], ["Media Note"])

        # Export zip includes assets/
        dest = Path(self._tmp.name) / "with_assets.zip"
        self.assertEqual(self.vault.export_zip(dest), 1)
        with zipfile.ZipFile(dest, "r") as zf:
            self.assertEqual(zf.read(f"alpha/{gif_path}"), gif_bytes)
            self.assertEqual(zf.read(f"alpha/{png_path}"), png_bytes)

        # Merge into a second vault preserves both notes and encrypted attachments
        cf.update_config("beta")
        self.assertTrue(cf.create_db("password-2", "beta"))
        target = Vault("beta", "password-2")
        try:
            source_db = cf.vault_path("alpha") / "alpha.db"
            imported, skipped = target.merge_database(source_db, "password-1")
            self.assertEqual((imported, skipped), (1, 0))
            self.assertEqual(target.get_attachment(gif_path), gif_bytes)
            self.assertEqual(target.get_attachment(png_path), png_bytes)
        finally:
            target.close()

    def test_filesystem_vault_obsidian_style_folders_notes_and_assets_on_disk(self):
        import io
        from PIL import Image

        parent_dir = Path(self._tmp.name) / "ObsidianRoot"
        vdir = cf.create_filesystem_vault("Workspace", parent_dir=parent_dir)
        self.assertTrue(cf.is_filesystem_vault("Workspace"))
        self.assertEqual(cf.get_vault_dir("Workspace"), vdir)
        self.assertTrue((vdir / "assets").is_dir())

        fs_vault = Vault("Workspace")
        try:
            self.assertFalse(fs_vault.is_encrypted)
            eng_id = fs_vault.create_folder("Engineering")
            specs_id = fs_vault.create_folder("Specs", eng_id)
            self.assertTrue((vdir / "Engineering" / "Specs").is_dir())
            with self.assertRaises(DuplicateNameError):
                fs_vault.create_folder("engineering", 0)

            nid = fs_vault.create_note("Architecture", "# V1", folder_id=specs_id)
            md_file = vdir / "Engineering" / "Specs" / "Architecture.md"
            self.assertTrue(md_file.is_file())
            self.assertEqual(md_file.read_text(encoding="utf-8"), "# V1")

            # Rename and update note -> renames .md file on disk
            fs_vault.save_note(nid, "System Design", "# V2", folder_id=specs_id)
            self.assertFalse(md_file.exists())
            renamed_file = vdir / "Engineering" / "Specs" / "System Design.md"
            self.assertTrue(renamed_file.is_file())
            self.assertEqual(renamed_file.read_text(encoding="utf-8"), "# V2")

            # Save an animated GIF attachment -> stored as real file in <vault>/assets/
            gif_buf = io.BytesIO()
            f1 = Image.new("RGBA", (20, 20), (255, 0, 0, 255))
            f2 = Image.new("RGBA", (20, 20), (0, 0, 255, 255))
            f1.save(gif_buf, format="GIF", save_all=True, append_images=[f2], duration=70, loop=0)
            gif_bytes = gif_buf.getvalue()
            rel_gif = fs_vault.save_attachment(gif_bytes, ".gif", "demo")
            self.assertTrue((vdir / rel_gif).is_file())
            self.assertEqual(fs_vault.get_attachment(rel_gif), gif_bytes)

            # Delete folder removes directory and notes on disk
            fs_vault.delete_folder(eng_id)
            self.assertFalse((vdir / "Engineering").exists())
            self.assertEqual(fs_vault.notes(), [])
        finally:
            fs_vault.close()

        cf.delete_vault("Workspace")
        self.assertFalse(vdir.exists())
        self.assertNotIn("Workspace", cf.read_config()[0])


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


class ImageAndGifEditorTests(unittest.TestCase):
    def test_markdown_and_wiki_image_tokens_and_backlink_exclusion(self):
        line = "See ![demo|320](assets/anim.gif) and ![[assets/photo.png|240]] plus [[RealNote]]."
        tokens = parse_inline(line)
        self.assertEqual([(t.kind, t.target) for t in tokens], [
            ("image", "assets/anim.gif"),
            ("image", "assets/photo.png"),
            ("wikilink", "RealNote"),
        ])
        self.assertEqual(Vault.links(line), {"RealNote"})

    def test_editor_controller_inserts_and_renders_images_and_animated_gifs(self):
        import io
        import tkinter as tk
        import customtkinter as ctk
        from PIL import Image
        from app.UI.brand import icon_image
        from app.UI.markdown_editor import MarkdownEditorController, serialize_pil_image

        root = tk.Tk()
        root.withdraw()
        try:
            # Verify the new image toolbar icon renders cleanly
            self.assertIsNotNone(icon_image("image", 16))

            store: dict[str, bytes] = {}

            def on_paste(raw: bytes, ext: str, hint: str) -> str:
                key = f"assets/{hint}{ext}"
                store[key] = raw
                return key

            textbox = ctk.CTkTextbox(root, width=600, height=400)
            ctrl = MarkdownEditorController(
                textbox,
                on_open_wikilink=lambda _t: None,
                on_modified=lambda: None,
                resolve_image=lambda target: store.get(target),
                on_paste_image=on_paste,
            )

            # Create a 3-frame animated GIF
            f1 = Image.new("RGBA", (60, 40), (255, 0, 0, 255))
            f2 = Image.new("RGBA", (60, 40), (0, 255, 0, 255))
            f3 = Image.new("RGBA", (60, 40), (0, 0, 255, 255))
            gif_buf = io.BytesIO()
            f1.save(gif_buf, format="GIF", save_all=True, append_images=[f2, f3], duration=60, loop=0)
            gif_img = Image.open(io.BytesIO(gif_buf.getvalue()))
            raw_gif, ext, hint = serialize_pil_image(gif_img)
            self.assertEqual(ext, ".gif")

            self.assertTrue(ctrl.insert_image_bytes(raw_gif, ext, "looping", render_now=True))
            content = textbox.get("1.0", "end-1c")
            self.assertIn("![looping](assets/looping.gif)", content)
            # Caret moved to line 2, so line 1 is off-cursor and rendered as an embedded animated GIF widget
            self.assertEqual(len(ctrl._embedded_widgets), 1)
            self.assertEqual(len(ctrl._gif_jobs), 1)
            media = next(iter(ctrl._media_cache.values()))
            self.assertTrue(media.is_gif)
            self.assertEqual(len(media.frames), 3)

            # Focusing line 1 hides the embedded widget so raw Markdown can be edited
            ctrl._focus_line(1, 0)
            ctrl.clear_media_cache()
            self.assertEqual(len(ctrl._gif_jobs), 0)
        finally:
            root.destroy()

    def test_editor_differential_render_avoids_full_refresh_and_reuses_widgets(self) -> None:
        import io
        from PIL import Image
        import customtkinter as ctk
        from app.UI.markdown_editor import MarkdownEditorController

        root = ctk.CTk()
        root.withdraw()
        try:
            textbox = ctk.CTkTextbox(root, width=600, height=400)
            textbox.pack()
            buf = io.BytesIO()
            Image.new("RGB", (40, 30), (20, 120, 220)).save(buf, format="PNG")
            assets = {"assets/pic.png": buf.getvalue()}

            ctrl = MarkdownEditorController(
                textbox,
                on_open_wikilink=lambda _t: None,
                on_modified=lambda: None,
                font_family="Segoe UI",
                resolve_image=lambda target: assets.get(target),
            )
            w = ctrl.widget
            doc = (
                "# Title Heading\n"
                "![pic](assets/pic.png)\n"
                "| Col A | Col B |\n"
                "| --- | --- |\n"
                "| 1 | 2 |\n"
                "Typing line"
            )
            w.insert("1.0", doc)
            w.mark_set("insert", "6.end")
            ctrl.render()

            self.assertEqual(len(ctrl._embedded_widgets), 2)
            initial_widgets = list(ctrl._embedded_widgets)

            # Spy on tag_add / tag_remove calls during incremental typing on line 6
            touched_indices: list[str] = []
            orig_add = w.tag_add
            orig_remove = w.tag_remove

            def spy_add(tag, index1, *args):
                touched_indices.append(str(index1))
                return orig_add(tag, index1, *args)

            def spy_remove(tag, index1, index2=None):
                touched_indices.append(str(index1))
                return orig_remove(tag, index1, index2)

            w.tag_add = spy_add
            w.tag_remove = spy_remove
            try:
                w.insert("insert", " more **bold** text")
                ctrl.render()
            finally:
                w.tag_add = orig_add
                w.tag_remove = orig_remove

            # Only line 6 should have been touched by tag operations; lines 1..5 must not be refreshed
            touched_lines = {int(idx.split(".")[0]) for idx in touched_indices if "." in idx}
            self.assertEqual(touched_lines, {6})

            # Embedded image and table widgets on lines 2..5 must be the exact same widget instances
            self.assertEqual(ctrl._embedded_widgets, initial_widgets)
            for child in initial_widgets:
                self.assertTrue(child.winfo_exists())
        finally:
            root.destroy()

    def test_filesystem_vault_rejects_duplicate_or_nested_vault_folder_paths(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            old_base = cf.base_path
            cf.base_path = tmp
            try:
                custom_folder = Path(tmp) / "UserSelectedFolder"
                vdir_a = cf.create_filesystem_vault("Alpha", parent_dir=custom_folder)
                self.assertTrue(vdir_a.is_dir())

                # Cannot create a second vault inside Alpha's vault directory (nested vault)
                with self.assertRaises(FileExistsError):
                    cf.create_filesystem_vault("Beta", parent_dir=vdir_a)

                # Cannot create a second vault inside the same custom folder chosen for Alpha
                with self.assertRaises(FileExistsError):
                    cf.create_filesystem_vault("Gamma", parent_dir=custom_folder)
            finally:
                cf.base_path = old_base

    def test_welcome_view_local_folder_row_opens_on_badge_and_row_clicks(self) -> None:
        import tempfile
        import customtkinter as ctk
        from main import MainApp

        with tempfile.TemporaryDirectory() as tmp:
            old_base = cf.base_path
            cf.base_path = tmp
            app = MainApp()
            app.withdraw()
            try:
                cf.create_filesystem_vault("u", parent_dir=Path(tmp) / "CustomRoot")
                app.show_frame("MainView", context={"vault_name": "u", "password": ""})
                app.update_idletasks()
                self.assertEqual(app.frames["MainView"].vault.name, "u")

                # Close/lock the local folder vault -> returns to WelcomeView
                app.frames["MainView"].lock(navigate=True)
                app.update_idletasks()
                self.assertIsNone(app.frames["MainView"].vault)

                wv = app.frames["WelcomeView"]
                row = wv.vault_list.winfo_children()[0]
                # Every CTkLabel in the row (icon, name label, and 'Local folder · Last opened' badge) must have <Button-1> bound
                labels = [child for child in row.winfo_children() if isinstance(child, ctk.CTkLabel)]
                self.assertGreaterEqual(len(labels), 3)
                for lbl in labels:
                    self.assertTrue(bool(lbl._label.bind("<Button-1>")), f"Missing <Button-1> on {lbl.cget('text')!r}")
            finally:
                app.destroy()
                cf.base_path = old_base

    def test_theme_switch_after_destroying_icon_widgets_preserves_live_icons_and_backgrounds(self) -> None:
        import customtkinter as ctk
        from app.UI.brand import icon_image
        from app.UI.styles import Colors, apply_color_theme

        ctk.set_appearance_mode("dark")
        apply_color_theme("default")
        root = ctk.CTk(fg_color=Colors.card)
        root.withdraw()
        try:
            # Create and destroy widgets using cached icons (simulating tree refresh / closing Settings)
            dead_lbl = ctk.CTkLabel(root, text="", image=icon_image("folder", 15))
            dead_lbl.pack()
            dead_btn = ctk.CTkButton(root, text="Import", image=icon_image("import", 15), fg_color="transparent")
            dead_btn.pack()
            root.update_idletasks()
            dead_lbl.destroy()
            dead_btn.destroy()

            # Create live widgets using the same cached icons
            live_lbl = ctk.CTkLabel(root, text="", image=icon_image("folder", 15))
            live_lbl.pack()
            live_btn = ctk.CTkButton(root, text="Import 2", image=icon_image("import", 15), fg_color="transparent")
            live_btn.pack()
            root.update_idletasks()

            # Switch to Monochrome + Light mode
            apply_color_theme("monochrome")
            ctk.set_appearance_mode("light")
            root.update_idletasks()

            # Live Tcl images must exist (no TclError: image "pyimage..." doesn't exist)
            lbl_img = live_lbl._label.cget("image")
            btn_img = live_btn._image_label.cget("image")
            self.assertEqual(root.tk.call("image", "type", lbl_img), "photo")
            self.assertEqual(root.tk.call("image", "type", btn_img), "photo")

            # Icon backgrounds must match light surface (no dark/black block left behind)
            self.assertEqual(live_btn._image_label.cget("bg"), live_btn._text_label.cget("bg"))
            self.assertEqual(live_lbl._label.cget("bg"), live_lbl._canvas.cget("bg"))
        finally:
            apply_color_theme("default")
            root.destroy()

    def test_sticky_note_mode_and_pin_toggle_shrinks_and_restores_workspace(self) -> None:
        import tempfile
        from main import MainApp

        with tempfile.TemporaryDirectory() as tmp:
            old_base = cf.base_path
            cf.base_path = tmp
            app = MainApp()
            app.withdraw()
            try:
                cf.create_filesystem_vault("StickyVault", parent_dir=Path(tmp) / "StickyRoot")
                app.show_frame("MainView", context={"vault_name": "StickyVault", "password": ""})
                app.update_idletasks()
                mv = app.frames["MainView"]

                self.assertFalse(mv.sticky_mode)
                self.assertFalse(mv.pinned)
                self.assertTrue(bool(mv.sidebar_frame.grid_info()))

                # Enter sticky note mode -> collapses sidebar & backlinks, pins window, shrinks geometry
                mv.toggle_sticky_mode()
                app.update_idletasks()
                self.assertTrue(mv.sticky_mode)
                self.assertTrue(mv.pinned)
                self.assertEqual(bool(app.attributes("-topmost")), True)
                self.assertEqual(mv.sidebar_frame.grid_info(), {})
                self.assertEqual(mv.context_panel.grid_info(), {})

                # Independent pin toggle while in sticky mode
                mv.toggle_pin_window()
                app.update_idletasks()
                self.assertTrue(mv.sticky_mode)
                self.assertFalse(mv.pinned)
                self.assertEqual(bool(app.attributes("-topmost")), False)

                # Re-pin, then exit sticky mode -> restores sidebar & unpins window
                mv.toggle_pin_window()
                self.assertTrue(mv.pinned)
                mv.toggle_sticky_mode()
                app.update_idletasks()
                self.assertFalse(mv.sticky_mode)
                self.assertFalse(mv.pinned)
                self.assertEqual(bool(app.attributes("-topmost")), False)
                self.assertTrue(bool(mv.sidebar_frame.grid_info()))
            finally:
                app.destroy()
                cf.base_path = old_base


if __name__ == "__main__":
    unittest.main()
