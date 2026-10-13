"""Actions-only acquisition of an exact public model revision; no local builds."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.request

from huggingface_hub import snapshot_download

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('Model acquisition and verification run only in GitHub Actions')

repository = 'Systran/faster-whisper-tiny'
revision = 'd90ca5fe260221311c53c58e660288d3deb8d356'
files = ['model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt', 'README.md']
snapshot = Path(snapshot_download(repo_id=repository, revision=revision, allow_patterns=files))
destination = Path('models/tiny')
destination.mkdir(parents=True, exist_ok=True)
for name in files:
    if not (snapshot / name).is_file():
        raise RuntimeError('Pinned model file missing: ' + name)
    shutil.copyfile(snapshot / name, destination / name)
card = (destination / 'README.md').read_text(encoding='utf-8')
if 'license: mit' not in card:
    raise RuntimeError('Pinned model card does not declare the expected license')
license_url = 'https://raw.githubusercontent.com/openai/whisper/86098128c0b4f24f0e2aa2994de830614b474227/LICENSE'
with urllib.request.urlopen(license_url, timeout=30) as response:
    license_bytes = response.read(8193)
if len(license_bytes) != 1063 or b'MIT License' not in license_bytes or b'Copyright (c) 2022 OpenAI' not in license_bytes:
    raise RuntimeError('Unexpected original Whisper license')
(destination / 'WHISPER-LICENSE').write_bytes(license_bytes)
manifest = {'model': repository, 'revision': revision, 'license': 'MIT', 'license_source': license_url,
            'source_commit': os.environ['GITHUB_SHA'],
            'files': {name: {'size': (destination / name).stat().st_size,
                             'sha256': hashlib.sha256((destination / name).read_bytes()).hexdigest()}
                      for name in files + ['WHISPER-LICENSE']}}
(destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
Path('evidence').mkdir(exist_ok=True)
Path('evidence/model.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps({'model': repository, 'revision': revision,
                  'bytes': sum(file['size'] for file in manifest['files'].values())}))
