"""Actions-only freezing of the original CLI, then its independent HTTP shell.

This integrates reviewed media, but is not yet a distributable app approval:
all other native dependencies and the installer still need complete gates.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import importlib.util

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('Build only in GitHub Actions')

root = Path(__file__).resolve().parents[1]
os.chdir(root)
source = root.parent / 'subtitle_tool.py'
media_target = 'win64' if os.name == 'nt' else 'linux64'
media = root / 'reviewed-media' / media_target
acquisition = json.loads((media.parent / 'acquisition.json').read_text(encoding='utf-8'))
if acquisition['product_commit'] != os.environ['GITHUB_SHA'] or not acquisition['all_files_verified']:
    raise ValueError('Need current hash-verified reviewed media')
media_manifest = json.loads((media / 'manifest.json').read_text(encoding='utf-8'))
if not (root / 'frontend' / 'index.html').is_file() or not (root / 'models/tiny/manifest.json').is_file():
    raise SystemExit('Build the locked UI and pinned local model first')

common = [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', '--onedir']
engine = common + ['--name', 'subtitle-engine', '--distpath', 'engine-dist', '--workpath', 'build-engine']
for module in ('faster_whisper', 'ctranslate2', 'av', 'onnxruntime', 'tokenizers', 'huggingface_hub'):
    engine += ['--collect-all', module]
# The GUI explicitly selects local CPU int8; do not ship an unused Torch/CUDA stack.
for module in ('torch', 'tensorflow', 'PyQt6', 'PySide6', 'webview', 'fastapi', 'uvicorn'):
    engine += ['--exclude-module', module]
subprocess.run(engine + [str(source)], check=True)
cpu_module = importlib.util.spec_from_file_location('cpu_payload', root / 'packaging/cpu-payload.py')
cpu_payload = importlib.util.module_from_spec(cpu_module)
cpu_module.loader.exec_module(cpu_payload)
cpu_receipt = cpu_payload.trim_optional_gpu(root / 'engine-dist/subtitle-engine')
# The original binary retains its independent tree. Its own fixed media path is
# copied in full, including any required DLLs, docs and upstream full license.
shutil.copytree(media / 'ffmpeg', root / 'engine-dist/subtitle-engine/_internal/media/ffmpeg', symlinks=True)
target = root / 'bin/subtitle-engine'
if target.exists():
    # A fixed generated build directory inside this checkout, never user files.
    if target.resolve().parent != (root / 'bin').resolve():
        raise ValueError('Unsafe generated engine directory')
    shutil.rmtree(target)
shutil.copytree(root / 'engine-dist/subtitle-engine', target, symlinks=True)
suffix = '.exe' if os.name == 'nt' else ''
binary = target / ('subtitle-engine' + suffix)
help_result = subprocess.run([str(binary), '--help'], check=True, capture_output=True)
if b'--transcribe-only' not in help_result.stdout or b'--local-only' not in help_result.stdout:
    raise ValueError('Frozen binary is not the intended original CLI')

app = common + ['--name', 'Lain42-Subtitle-Studio', '--add-data', 'frontend:frontend',
                '--add-data', 'models:models', '--collect-submodules', 'uvicorn']
for module in ('faster_whisper', 'ctranslate2', 'av', 'onnxruntime', 'tokenizers', 'torch', 'tensorflow'):
    app += ['--exclude-module', module]
if os.name == 'nt':
    for module in ('webview', 'pythonnet', 'clr_loader'):
        app += ['--collect-all', module]
    for module in ('PyQt6', 'PySide6', 'gi'):
        app += ['--exclude-module', module]
else:
    app += ['--exclude-module', 'webview']
subprocess.run(app + ['launcher.py'], check=True)

packed = root / 'dist/Lain42-Subtitle-Studio'
# Preserve the separate worker's entire onedir layout and executable/symlink modes.
shutil.copytree(target, packed / '_internal/bin/subtitle-engine', symlinks=True)
corresponding = packed / 'third-party/ffmpeg'
shutil.copytree(media / 'sources', corresponding / 'sources', symlinks=True)
shutil.copyfile(media / 'manifest.json', corresponding / 'manifest.json')
shutil.copyfile(media / 'ffmpeg/LICENSE.txt', corresponding / 'LICENSE.txt')
shutil.copyfile(media.parent / 'acquisition.json', corresponding / 'acquisition.json')
for name, record in media_manifest['files'].items():
    if name.startswith('ffmpeg/'):
        copied = packed / '_internal/bin/subtitle-engine/_internal/media' / name
    elif name.startswith('sources/'):
        copied = corresponding / name
    else:
        raise ValueError('Unexpected media layout: ' + name)
    if hashlib.sha256(copied.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError('Packaged media/source differs: ' + name)
packed_engine = packed / '_internal/bin/subtitle-engine' / binary.name
if hashlib.sha256(packed_engine.read_bytes()).digest() != hashlib.sha256(binary.read_bytes()).digest():
    raise ValueError('Shell must carry the exact original frozen engine')
receipt = {'commit': os.environ['GITHUB_SHA'], 'runner': os.environ['RUNNER_OS'],
           'original_cli_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
           'engine_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
           'engine_files': {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in target.rglob('*') if p.is_file()},
           'independent_engine_binary': True, 'source_fallback_allowed': False,
           'media_source': 'Exact reviewed standalone FFmpeg with complete corresponding source archives',
           'media_acquisition': acquisition, 'complete_media_sources_in_app': True,
           'cpu_payload': cpu_receipt,
           'distributable': False}
Path('evidence').mkdir(exist_ok=True)
Path('evidence/frozen-build.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')

