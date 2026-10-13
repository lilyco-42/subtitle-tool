"""CI-owned source fixtures: provenance requires full identical native bytes."""
import importlib.util
import tempfile
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('runtime_sources',
    Path(__file__).resolve().parents[1] / 'desktop/packaging/runtime-sources.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeSourceTests(unittest.TestCase):
    def test_actual_installation_and_extensions_are_matched_without_site_packages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'DLLs').mkdir()
            (root / 'Lib/site-packages/other').mkdir(parents=True)
            (root / 'python312.dll').write_bytes(b'own real runtime fixture')
            (root / 'DLLs/_ssl.pyd').write_bytes(b'own extension fixture')
            (root / 'Lib/site-packages/other/unknown.dll').write_bytes(b'not a Python runtime')
            index = runtime.installed_runtime_index(root)
            self.assertEqual(2, len(index))
            record = next(x for values in index.values() for x in values
                          if x['installation_relative_path'] == 'DLLs/_ssl.pyd')
            self.assertFalse(record['redistribution_permission_inferred'])
            self.assertEqual(21, record['size'])

    def test_same_basename_with_different_bytes_does_not_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'python312.dll').write_bytes(b'original runtime bytes')
            index = runtime.installed_runtime_index(root)
            changed = runtime.hashlib.sha256(b'changed runtime bytes').hexdigest()
            self.assertNotIn(changed, index)

    def test_extension_folder_outside_installation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'python').mkdir()
            with self.assertRaises(ValueError):
                runtime.installed_runtime_index(root / 'python', root)

    def test_complete_installed_notice_kept_as_original_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = b'Own complete notice fixture.\n' * 100
            (root / 'LICENSE.txt').write_bytes(data)
            notice = runtime.installation_notices(root)['LICENSE.txt']
            self.assertEqual(data, notice['text'].encode())
            self.assertEqual(runtime.hashlib.sha256(data).hexdigest(), notice['sha256'])
            (root / 'LICENSE.txt').write_bytes(b'SPDX only')
            with self.assertRaises(ValueError):
                runtime.installation_notices(root)

    def test_missing_original_installation_license_is_not_fabricated(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                runtime.installation_notices(temporary)
