import gc
import tempfile
import unittest
from pathlib import Path

import secure_storage

import app.core.config as cf
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


if __name__ == "__main__":
    unittest.main()
