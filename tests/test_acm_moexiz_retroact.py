import json
import tempfile
import unittest
from pathlib import Path

import acm_moexiz_retroact as acm


class ExtractionTests(unittest.TestCase):
    def test_extract_and_deduplicate_with_categories(self):
        text = "GitHub https://GITHUB.com/NickelRamQc94/Repo. Again https://github.com/NickelRamQc94/Repo. Drive https://drive.google.com/drive/folders/abc"
        rows, rejected = acm.extract_records(text)
        self.assertEqual(rejected, 0)
        self.assertEqual(len(rows), 2)
        github = next(row for row in rows if row["category"] == "github")
        self.assertEqual(github["occurrences"], 2)
        self.assertEqual(github["url"], "https://github.com/NickelRamQc94/Repo")

    def test_credential_urls_are_not_exported(self):
        rows, rejected = acm.extract_records("https://user:password@example.com/private")
        self.assertEqual(rows, [])
        self.assertEqual(rejected, 1)

    def test_expert_mix_is_normalized_and_deterministic(self):
        mix = acm.expert_mix("algorithme et preuve; algorithme, statistique")
        self.assertEqual(mix, acm.expert_mix("algorithme et preuve; algorithme, statistique"))
        self.assertAlmostEqual(sum(mix.values()), 1.0)
        self.assertGreater(mix["analyst"], 0)

    def test_analyze_and_reproducible_serialization(self):
        raw = "Repo https://github.com/example/project".encode()
        first, stats1 = acm.analyze(raw.decode(), raw)
        second, stats2 = acm.analyze(raw.decode(), raw)
        self.assertEqual(stats1, stats2)
        self.assertEqual(json.dumps(first, ensure_ascii=False, sort_keys=True),
                         json.dumps(second, ensure_ascii=False, sort_keys=True))

    def test_retroact_diff_is_read_only_set_difference(self):
        current = {"sources": [{"url": "https://example.com/new"}]}
        with tempfile.TemporaryDirectory() as tmp:
            baseline = Path(tmp) / "old.json"
            baseline.write_text(json.dumps({"sources": [{"url": "https://example.com/old"}]}), encoding="utf-8")
            diff = acm.compare_previous(current, baseline)
        self.assertEqual(diff["added"], ["https://example.com/new"])
        self.assertEqual(diff["removed"], ["https://example.com/old"])
        self.assertEqual(diff["unchanged"], [])

    def test_output_manifest_hashes(self):
        raw = b"https://example.com"
        db, stats = acm.analyze(raw.decode(), raw)
        diff = acm.compare_previous(db, None)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            acm.write_outputs(db, stats, diff, out, "sample.txt")
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            for name, digest in manifest["outputs_sha256"].items():
                self.assertEqual(acm.sha256_bytes((out / name).read_bytes()), digest)


if __name__ == "__main__":
    unittest.main()
