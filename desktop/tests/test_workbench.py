import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import zipfile

from fastapi.testclient import TestClient
from studio.app import create_app
from studio.captions import document
from fixtures import fixtures, speech


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.video, self.subtitle = fixtures(Path(self.directory.name))
        self.app = create_app()
        self.client = self.enterContext(TestClient(self.app, base_url='http://127.0.0.1:8057'))
        self.assertEqual(200, self.client.get('/').status_code)

    def upload(self, video=None, subtitle=True):
        source = video or self.video
        files = [('videos', (source.name, source.read_bytes(), 'video/mp4'))]
        if subtitle:
            files.append(('subtitle', ('own.srt', self.subtitle.read_bytes(), 'application/x-subrip')))
        response = self.client.post('/api/workspaces', files=files)
        self.assertEqual(200, response.status_code, response.text)
        return response.json()['id']

    def complete(self, request):
        response = self.client.post('/api/jobs', json=request)
        self.assertEqual(200, response.status_code, response.text)
        identifier = response.json()['id']
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            result = self.client.get('/api/jobs/' + identifier).json()
            if result['state'] not in {'queued', 'running'}:
                self.assertEqual('done', result['state'], result)
                return result
            time.sleep(.05)
        self.fail('Original CLI task did not finish')

    def test_caption_edit_real_soft_export_and_clear(self):
        session = self.upload()
        prefix = f'/api/workspaces/{session}/captions/0'
        caption = self.client.get(prefix).json()
        self.assertEqual(1, caption['count'])
        text = caption['text'].replace('NEW CAPTION', 'EDITED CAPTION')
        self.assertEqual(200, self.client.put(prefix, json={'text': text}).status_code)
        result = self.complete({'session': session, 'index': 0, 'mode': 'soft', 'container': 'mp4'})
        data = self.client.get(f'/api/jobs/{result["id"]}/files/export.zip').content
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual({'subtitles.srt', 'video.mp4'}, set(archive.namelist()))
            self.assertIn('EDITED CAPTION', archive.read('subtitles.srt').decode())
            output = Path(self.directory.name) / 'actual.mp4'
            output.write_bytes(archive.read('video.mp4'))
        captions = subprocess.run(['ffmpeg', '-nostdin', '-i', str(output), '-map', '0:s:0', '-f', 'srt', '-'],
                                  check=True, capture_output=True, text=True).stdout
        self.assertIn('EDITED CAPTION', captions)
        owned = self.app.state.workspaces.get(session)['root']
        self.assertEqual(200, self.client.delete('/api/workspaces/' + session).status_code)
        self.assertFalse(owned.exists())
        self.assertEqual(404, self.client.get('/api/jobs/' + result['id']).status_code)

    def test_local_cpu_transcription_uses_original_engine_and_real_model(self):
        video = speech(Path(self.directory.name))
        session = self.upload(video, subtitle=False)
        result = self.complete({'session': session, 'index': 0, 'mode': 'transcribe', 'language': 'en'})
        caption = self.client.get(f'/api/workspaces/{session}/captions/0').json()
        self.assertGreater(caption['count'], 0)
        self.assertIn('subtitle', caption['text'].lower())
        self.assertIn('cpu', result['log'])
        Path('evidence').mkdir(exist_ok=True)
        Path('evidence/actual-transcript.json').write_text(json.dumps({
            'synthetic_own_fixture': True, 'original_cli': True, 'local_cpu': True,
            'transcript': caption['text'], 'count': caption['count']}), encoding='utf-8')

    def test_origin_cookie_isolation_and_invalid_documents(self):
        self.assertEqual(403, self.client.get('/api/capabilities', headers={'Origin': 'https://other.invalid'}).status_code)
        other = self.enterContext(TestClient(create_app(), base_url='http://127.0.0.1:8057'))
        other.cookies.update(self.client.cookies)
        self.assertEqual(403, other.get('/api/capabilities').status_code)
        self.assertEqual(403, self.client.get('/api/capabilities', headers={'Host': 'evil.invalid'}).status_code)
        session = self.upload()
        self.assertEqual(400, self.client.put(f'/api/workspaces/{session}/captions/0', json={'text': 'invalid'}).status_code)
        self.assertEqual(422, self.client.post('/api/jobs', json={'session': session, 'index': 0, 'mode': 'hard', 'command': 'arbitrary'}).status_code)
        self.assertEqual(400, self.client.post('/api/jobs', json={'session': session, 'index': 2, 'mode': 'hard'}).status_code)
        with self.assertRaises(ValueError):
            document('1\n00:00:02,000 --> 00:00:01,000\nInvalid time\n\n')


if __name__ == '__main__':
    unittest.main()
