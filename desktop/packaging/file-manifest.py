"""Actions-only inventory of all candidate app bytes before installation tests."""
import hashlib
import json
import os
from pathlib import Path

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('Product manifests only in GitHub Actions')
root = Path('dist/Lain42-Subtitle-Studio').resolve()
if not (root / '_internal/bin/subtitle-engine').is_dir() or not (root / 'third-party/ffmpeg/sources').is_dir():
    raise ValueError('Need the complete original worker and corresponding media sources')
manifest_path = root / 'manifest.json'
if manifest_path.exists():
    raise ValueError('Do not overwrite an earlier package manifest')
files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted(root.rglob('*')) if p.is_file()}
manifest = {'commit': os.environ['GITHUB_SHA'], 'files': files,
            'complete_file_inventory': True, 'redistribution_audit_complete': False,
            'remaining_gate': 'All ASR/PyAV native dependencies need corresponding notices and sources'}
manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
Path('evidence').mkdir(exist_ok=True)
Path('evidence/package-inventory.json').write_text(json.dumps({
    'commit': os.environ['GITHUB_SHA'], 'files': len(files),
    'total_bytes': sum((root / p).stat().st_size for p in files),
    'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    'redistribution_audit_complete': False}), encoding='utf-8')
