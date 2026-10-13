"""Actions-only freezing of the original CLI, then its independent HTTP shell.

This is a frozen-engine verification stage, not a distributable media release.
FFmpeg is still supplied by the CI host until its source/notice gate is complete.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('Build only in GitHub Actions')

root = Path(__file__).resolve().parents[1]
os.chdir(root)
source = root.parent / 'subtitle_tool.py'
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
packed_engine = packed / '_internal/bin/subtitle-engine' / binary.name
if hashlib.sha256(packed_engine.read_bytes()).digest() != hashlib.sha256(binary.read_bytes()).digest():
    raise ValueError('Shell must carry the exact original frozen engine')
receipt = {'commit': os.environ['GITHUB_SHA'], 'runner': os.environ['RUNNER_OS'],
           'original_cli_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
           'engine_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
           'engine_files': {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in target.rglob('*') if p.is_file()},
           'independent_engine_binary': True, 'source_fallback_allowed': False,
           'media_source': 'CI host FFmpeg; NOT bundled or approved for redistribution',
           'distributable': False}
Path('evidence').mkdir(exist_ok=True)
Path('evidence/frozen-build.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')

