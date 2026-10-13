"""Original embedded notices are preserved; tags alone are not approvals."""
import importlib.util
import io
import os
from pathlib import Path
import tarfile
import types
import unittest
from unittest.mock import patch

with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'lilyco-42/subtitle-tool'}):
    spec = importlib.util.spec_from_file_location('native_attribution', Path(__file__).resolve().parents[1] / 'desktop/packaging/native-attribution.py')
    attribution = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(attribution)


def source_archive(name, data):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        member = tarfile.TarInfo(name)
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
    return output.getvalue()


class OriginalNoticeTests(unittest.TestCase):
    def test_transient_source_dns_failure_retries_without_changing_bytes(self):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'original pinned source bytes'
        with patch.object(attribution.urllib.request, 'urlopen', side_effect=[
                attribution.urllib.error.URLError('own DNS fixture'), response]) as fetcher, \
                patch.object(attribution.time, 'sleep') as sleep:
            self.assertEqual(b'original pinned source bytes', attribution.fetch('https://example.invalid/source'))
            self.assertEqual(2, fetcher.call_count)
            sleep.assert_called_once_with(2)

    def test_source_access_denial_is_not_retried(self):
        denial = attribution.urllib.error.HTTPError('https://example.invalid/source', 403, 'own fixture', None, None)
        with patch.object(attribution.urllib.request, 'urlopen', side_effect=denial) as fetcher, \
                patch.object(attribution.time, 'sleep') as sleep, self.assertRaises(attribution.urllib.error.HTTPError):
            attribution.fetch('https://example.invalid/source')
        self.assertEqual(1, fetcher.call_count)
        sleep.assert_not_called()

    def test_source_retry_budget_is_bounded(self):
        with patch.object(attribution.urllib.request, 'urlopen', side_effect=attribution.urllib.error.URLError('own fixture')) as fetcher, \
                patch.object(attribution.time, 'sleep') as sleep, self.assertRaises(attribution.urllib.error.URLError):
            attribution.fetch('https://example.invalid/source')
        self.assertEqual(3, fetcher.call_count)
        self.assertEqual([2, 4], [call.args[0] for call in sleep.call_args_list])

    def test_pinned_core_metadata_is_used_without_top_level_export(self):
        record = {'version': (62, 1, 0), 'configuration': b'own fixture', 'license': b'own fixture'}
        actual = {name: record for name in ('libavutil', 'libavcodec', 'libavformat',
                                           'libavdevice', 'libavfilter', 'libswscale', 'libswresample')}
        core = types.ModuleType('av._core')
        core.library_meta = actual
        with patch.dict('sys.modules', {'av': types.ModuleType('av'), 'av._core': core}):
            self.assertIs(actual, attribution.av_library_metadata())

    def test_missing_native_metadata_is_rejected(self):
        core = types.ModuleType('av._core')
        core.library_meta = {}
        with patch.dict('sys.modules', {'av': types.ModuleType('av'), 'av._core': core}), self.assertRaises(ValueError):
            attribution.av_library_metadata()

    def test_full_original_header_notice_is_kept_byte_for_byte(self):
        license_bytes = (Path(__file__).resolve().parents[1] / 'LICENSE').read_bytes()
        data = b'/*\n' + license_bytes + b'*/\nvoid own_fixture(void);\n'
        result = attribution.original_notices(source_archive('include/fixture.h', data))
        self.assertEqual(data, result['include/fixture.h']['text'].encode('utf-8'))
        self.assertEqual(attribution.sha(data), result['include/fixture.h']['sha256'])

    def test_spdx_or_copyright_without_full_notice_is_rejected(self):
        for data in (b'/* SPDX-License-Identifier: MIT */', b'/* Copyright (c) 2026 */'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                attribution.original_notices(source_archive('include/fixture.h', data))

    def test_named_original_license_still_is_kept(self):
        data = (Path(__file__).resolve().parents[1] / 'LICENSE').read_bytes()
        result = attribution.original_notices(source_archive('source/LICENSE', data))
        self.assertEqual(data, result['source/LICENSE']['text'].encode('utf-8'))
