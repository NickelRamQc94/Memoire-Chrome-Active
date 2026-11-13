import tempfile
import unittest
from pathlib import Path

import acm_bridge


class BridgeTests(unittest.TestCase):
    def test_build_index_and_search_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "archive.txt"
            source.write_text(
                "Willow qubit algorithm https://github.com/example/willow-project\n"
                "Drive notes https://drive.google.com/drive/folders/demo\n",
                encoding="utf-8",
            )
            index = acm_bridge.build_index(source)
        self.assertEqual(index["unique_urls"], 2)
        hits = acm_bridge.search(index, "Willow qubit")
        self.assertTrue(hits)
        self.assertIn("willow-project", hits[0]["url"])

    def test_exact_url_has_priority(self):
        index = {
            "records": [
                {"id": "a", "url": "https://example.com/a", "category": "other_web", "occurrences": 1, "first_offset": 0, "context_examples": []},
                {"id": "b", "url": "https://example.com/b", "category": "other_web", "occurrences": 1, "first_offset": 10, "context_examples": []},
            ],
            "postings": {},
        }
        self.assertEqual(acm_bridge.search(index, "https://example.com/a")[0]["id"], "a")

    def test_export_contains_provenance_and_manual_import_notice(self):
        index = {"source_name": "archive.txt", "source_sha256": "abc", "unique_urls": 1}
        hits = [{"score": 1.0, "category": "github", "url": "https://github.com/a/b", "id": "x", "occurrences": 1, "first_offset": 4, "context_examples": ["context"]}]
        note = acm_bridge.notebooklm_note(index, "test", hits)
        self.assertIn("SHA-256", note)
        self.assertIn("Import manuel requis", note)
        self.assertIn("https://github.com/a/b", note)


if __name__ == "__main__":
    unittest.main()
