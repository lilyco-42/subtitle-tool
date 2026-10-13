"""Hash-match frozen runtime files to the actual CI Python installation.

Origin evidence is separate from redistribution permission. System runtimes,
unmatched files and transitive component licenses must still be reviewed.
"""
import hashlib
from pathlib import Path


def installed_runtime_index(installation, extension_directory=None):
    installation = Path(installation).resolve()
    folders = [installation, installation / 'DLLs']
    if extension_directory is not None:
        extension = Path(extension_directory).resolve()
        if not extension.is_relative_to(installation):
            raise ValueError('Python extension directory escapes its installation')
        folders.append(extension)
    index = {}
    for folder in dict.fromkeys(folders):
        if not folder.is_dir():
            continue
        for file in sorted(folder.iterdir()):
            if (not file.is_file() or file.is_symlink()
                    or not file.resolve().is_relative_to(installation)
                    or (file.suffix.lower() not in {'.dll', '.pyd', '.so', '.dylib'}
                        and '.so.' not in file.name)):
                continue
            data = file.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            index.setdefault(digest, []).append({
                'installation_relative_path': file.relative_to(installation).as_posix(),
                'sha256': digest, 'size': len(data),
                'source_kind': 'Actual CI CPython installation',
                'redistribution_permission_inferred': False,
            })
    return index


def installation_notices(installation):
    installation = Path(installation).resolve()
    notices = {}
    for name in ('LICENSE', 'LICENSE.txt'):
        file = installation / name
        if not file.is_file() or file.is_symlink():
            continue
        data = file.read_bytes()
        if len(data) < 1000:
            raise ValueError('Python installation license is incomplete')
        notices[name] = {'sha256': hashlib.sha256(data).hexdigest(),
                         'text': data.decode('utf-8'), 'size': len(data)}
    if not notices:
        raise ValueError('Actual Python installation has no complete license')
    return notices
