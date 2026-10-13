"""Remove only optional GPU data from this explicitly CPU-int8 product in Actions.

Never strip a directly imported runtime: if the wheel requires one, the build
fails and a real CPU wheel is needed. Original offline ASR is tested afterwards.
"""
import hashlib
import json
import os
from pathlib import Path


def trim_optional_gpu(root):
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Package inspection only in GitHub Actions')
    if os.name != 'nt':
        return {'platform': 'Linux', 'removed_optional_gpu_files': []}
    import pefile
    root = root.resolve()
    directory = root / '_internal/ctranslate2'
    optional = [p for p in directory.glob('*.dll')
                if p.name.lower().startswith(('cudnn', 'cublas', 'cudart', 'nvrtc', 'nvjitlink'))]
    names = {p.name.lower() for p in optional}
    imports = []
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in {'.dll', '.pyd'} or path in optional:
            continue
        with pefile.PE(str(path), fast_load=True) as image:
            image.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
                pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
            for entry in list(getattr(image, 'DIRECTORY_ENTRY_IMPORT', [])) + list(getattr(image, 'DIRECTORY_ENTRY_DELAY_IMPORT', [])):
                name = entry.dll.decode('ascii').lower()
                if name in names:
                    imports.append({'file': path.relative_to(root).as_posix(), 'requires': name})
    if imports:
        raise ValueError('CPU product still imports GPU libraries; build a CPU wheel instead: ' + json.dumps(imports))
    records = []
    for path in optional:
        if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink():
            raise ValueError('GPU file escapes the generated package')
        records.append({'path': path.relative_to(root).as_posix(), 'size': path.stat().st_size,
                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        path.unlink()
    return {'platform': 'Windows', 'no_direct_or_delay_gpu_imports': True,
            'removed_optional_gpu_files': records, 'offline_cpu_asr_verification_required': True}
