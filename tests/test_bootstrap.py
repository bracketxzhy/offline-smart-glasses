import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import setup_models


class BootstrapTests(unittest.TestCase):
    def test_corrupted_cached_asset_is_redownloaded_not_recertified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            source.write_bytes(b"valid model tokens")
            target = root / "models/tokens.txt"
            target.parent.mkdir()
            target.write_bytes(b"")
            url = source.as_uri()
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            (root / "models/manifest.json").write_text(json.dumps([{"path": "models/tokens.txt", "url": url, "bytes": 18, "sha256": expected}]))
            with patch.object(setup_models, "ROOT", root):
                record = setup_models.download(("models/tokens.txt", url, None))
            self.assertEqual(target.read_bytes(), b"valid model tokens")
            self.assertEqual(record["sha256"], expected)


if __name__ == "__main__":
    unittest.main()
