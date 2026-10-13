"""Actual frozen CLI + shell acceptance, only in Actions, no source fallback."""
import io
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import httpx
import psutil
from fixtures import fixtures, speech

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('Frozen product verification only in GitHub Actions')

binary = Path(sys.argv[1]).resolve()
engine_name = 'subtitle-engine.exe' if os.name == 'nt' else 'subtitle-engine'
expected_engine = binary.parent / '_internal/bin/subtitle-engine' / engine_name
assert expected_engine.is_file(), 'Missing original frozen CLI'
env = dict(os.environ)
env.pop('LAIN42_SUBTITLE_SOURCE_ENGINE', None)
env['HF_HUB_OFFLINE'] = '1'
env['TRANSFORMERS_OFFLINE'] = '1'
env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    receipt_path = root / 'startup.json'
    env['LAIN42_SUBTITLE_RECEIPT'] = str(receipt_path)
    process = subprocess.Popen([str(binary), '--browser'], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, env=env)
    lines, seen = queue.Queue(), []

    def collect():
        for line in process.stdout:
            text = line.decode('utf-8', errors='replace')
            lines.put(text)
            seen.append(text)

    threading.Thread(target=collect, daemon=True).start()
    try:
        url = None
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Frozen shell exited before startup: ' + ''.join(seen))
            try:
                found = re.search(r'http://127\.0\.0\.1:\d+/', lines.get(timeout=.2))
                if found:
                    url = found[0]
                    break
            except queue.Empty:
                pass
        assert url, ''.join(seen)
        with httpx.Client(base_url=url, timeout=30, trust_env=False) as client:
            for _ in range(150):
                try:
                    client.get('/').raise_for_status()
                    break
                except httpx.HTTPError:
                    time.sleep(.2)
            else:
                raise RuntimeError('Frozen loopback server never became ready')
            caps = client.get('api/capabilities').json()
            assert caps['engine'] and caps['model'] and caps['model_device'] == 'cpu', caps
            assert receipt_path.is_file(), 'Missing actual owned workspace receipt'
            startup = json.loads(receipt_path.read_text(encoding='utf-8'))
            assert startup['frozen'] is True and startup['url'] == url
            assert Path(startup['engine']).resolve() == expected_engine.resolve()
            workspace_root = Path(startup['workspace_root'])
            assert workspace_root.is_dir()
            children_observed = set()

            def complete(request):
                response = client.post('api/jobs', json=request)
                response.raise_for_status()
                identifier = response.json()['id']
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    for child in psutil.Process(process.pid).children(recursive=True):
                        try:
                            if Path(child.exe()).resolve() == expected_engine.resolve():
                                children_observed.add(child.pid)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    job = client.get('api/jobs/' + identifier).json()
                    if job['state'] not in {'queued', 'running'}:
                        assert job['state'] == 'done', job
                        return job
                    time.sleep(.05)
                raise RuntimeError('Frozen original CLI did not finish: ' + str(job))

            def upload(video, subtitle=None):
                files = [('videos', (video.name, video.read_bytes(), 'video/mp4'))]
                if subtitle:
                    files.append(('subtitle', ('own.srt', subtitle.read_bytes(), 'application/x-subrip')))
                response = client.post('api/workspaces', files=files)
                response.raise_for_status()
                return response.json()['id']

            video, subtitle = fixtures(root)
            session = upload(video, subtitle)
            prefix = f'api/workspaces/{session}/captions/0'
            edited = client.get(prefix).json()['text'].replace('NEW CAPTION', 'FROZEN ORIGINAL CLI')
            client.put(prefix, json={'text': edited}).raise_for_status()
            soft = complete({'session': session, 'index': 0, 'mode': 'soft', 'container': 'mp4'})
            exported = client.get(f'api/jobs/{soft["id"]}/files/export.zip').content
            with zipfile.ZipFile(io.BytesIO(exported)) as archive:
                assert set(archive.namelist()) == {'video.mp4', 'subtitles.srt'}
                assert archive.read('subtitles.srt').decode() == edited
                output = root / 'soft.mp4'
                output.write_bytes(archive.read('video.mp4'))
            text = subprocess.run(['ffmpeg', '-nostdin', '-i', str(output), '-map', '0:s:0', '-f', 'srt', '-'],
                                  check=True, capture_output=True, text=True).stdout
            assert 'FROZEN ORIGINAL CLI' in text
            hard = complete({'session': session, 'index': 0, 'mode': 'hard', 'container': 'mp4', 'font': 'DejaVu Sans'})
            hard_output = root / 'hard.mp4'
            hard_output.write_bytes(client.get(f'api/jobs/{hard["id"]}/files/video.mp4').content)

            def frame(path):
                return subprocess.run(['ffmpeg', '-nostdin', '-ss', '1', '-i', str(path), '-frames:v', '1',
                                       '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], check=True, capture_output=True).stdout

            assert len(frame(hard_output)) == 320 * 240 * 3 and frame(hard_output) != frame(video)
            spoken = speech(root)
            asr_session = upload(spoken)
            asr = complete({'session': asr_session, 'index': 0, 'mode': 'transcribe', 'language': 'en'})
            transcript = client.get(f'api/workspaces/{asr_session}/captions/0').json()
            assert transcript['count'] > 0 and 'subtitle' in transcript['text'].lower(), transcript
            assert 'cpu' in asr['log'] and children_observed, 'No real bundled CPU process was observed'
            assert client.get('api/capabilities', headers={'Origin': 'https://other.invalid'}).status_code == 403
            for item in (session, asr_session):
                client.delete('api/workspaces/' + item).raise_for_status()
            assert client.get('api/jobs/' + soft['id']).status_code == 404
            assert not list(workspace_root.iterdir()), 'Workspace clear must remove actual private media'
            remaining = psutil.Process(process.pid).children(recursive=True)
            assert not any(c.name().lower() in {'subtitle-engine', 'subtitle-engine.exe', 'ffmpeg', 'ffmpeg.exe'}
                           for c in remaining), 'Owned processing children must finish'
            Path('evidence').mkdir(exist_ok=True)
            Path('evidence/frozen-smoke.json').write_text(json.dumps({
                'commit': os.environ['GITHUB_SHA'], 'frozen_app': True, 'source_fallback_disabled': True,
                'observed_original_engine_pids': sorted(children_observed), 'local_model_cpu_asr': True,
                'own_synthetic_transcript': transcript['text'], 'edited_soft_track': True,
                'actual_hard_pixels': True, 'real_zip_contents': True, 'clear_private_files': True,
                'processing_children_exited': True, 'cross_origin_denied': True,
                'media_source': 'CI host, not bundled', 'distributable': False}), encoding='utf-8')
    finally:
        process.terminate()
        process.wait(timeout=30)
        if process.returncode not in {0, -15, 1}:
            print('Frozen verification process exit:', process.returncode, ''.join(seen))

