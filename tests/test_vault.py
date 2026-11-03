import gc
import tempfile
import unittest

import secure_storage

from app.core.vault import Vault


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


if __name__ == "__main__":
    unittest.main()
