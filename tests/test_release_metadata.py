import importlib.util
from pathlib import Path
import tempfile
import json
import unittest
spec=importlib.util.spec_from_file_location('release_metadata',Path(__file__).resolve().parents[1]/'.github/scripts/release_metadata.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class Tests(unittest.TestCase):
    def test_current_release(self):
        values,notes=module.metadata(Path(__file__).resolve().parents[1])
        self.assertEqual(values['tag'],'v0.1.0-beta.4')
        self.assertEqual(values['prerelease'],'true')
        self.assertIn('browser sign-in',notes);self.assertNotIn('Initial read-only',notes)
    def test_tag_mismatch_rejected(self):
        with self.assertRaises(ValueError):module.metadata(Path(__file__).resolve().parents[1],'v9.9.9')
    def test_stable_and_missing_notes(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);(p/'custom_components/bord_gais_energy').mkdir(parents=True)
            (p/'custom_components/bord_gais_energy/manifest.json').write_text(json.dumps({'version':'1.0.0'}))
            (p/'CHANGELOG.md').write_text('## 1.0.0\n\nStable release.\n')
            self.assertEqual(module.metadata(p)[0]['prerelease'],'false')
            (p/'CHANGELOG.md').write_text('## 0.1.0\nOld notes\n')
            with self.assertRaises(ValueError):module.metadata(p)
