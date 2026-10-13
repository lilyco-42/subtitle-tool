"""The frozen engine must select its own media before any host installation."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import subtitle_tool


class MediaResolutionTests(unittest.TestCase):
    def test_packaged_media_overrides_different_host_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'media/ffmpeg/bin'
            folder.mkdir(parents=True)
            (folder / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')).write_bytes(b'fixture-only')
            with patch.object(sys, '_MEIPASS', str(root), create=True), \
                    patch.dict(os.environ, {'PATH': 'different-host-media'}), \
                    patch.object(subtitle_tool.shutil, 'which', return_value='different-host-media/ffmpeg'):
                subtitle_tool.check_deps(require_asr=False)
                self.assertEqual(str(folder), os.environ['PATH'].split(os.pathsep)[0])

    def test_source_cli_keeps_host_installation_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(sys, '_MEIPASS', temporary, create=True), \
                    patch.dict(os.environ, {'PATH': 'existing-host-media'}), \
                    patch.object(subtitle_tool.shutil, 'which', return_value='existing-host-media/ffmpeg'):
                subtitle_tool.check_deps(require_asr=False)
                self.assertEqual('existing-host-media', os.environ['PATH'])

    def test_no_media_still_fails_without_faking_capability(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(sys, '_MEIPASS', temporary, create=True), \
                    patch.object(subtitle_tool.shutil, 'which', return_value=None):
                with self.assertRaises(SystemExit) as error:
                    subtitle_tool.check_deps(require_asr=False)
                self.assertEqual(1, error.exception.code)
