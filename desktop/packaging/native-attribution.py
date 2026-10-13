"""Actions-only original notices, PyAV media sources and actual native inventory.

This records unresolved runtime attribution explicitly. It is not a blanket
legal approval and must not be used to publish while unresolved items remain.
"""
import ast
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import urllib.request

if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != 'lilyco-42/subtitle-tool':
    raise SystemExit('Distribution audit only in this repository Actions')

ROOT = Path('dist/Lain42-Subtitle-Studio').resolve()
OUT = ROOT / 'third-party'
BUILDER = 'fab22bcb12748a05f86683ac632fdb96994d970e'
BUILDER_SCRIPT_SHA = 'ff4331e77f841b84b2f0369a6cd4dd8112b4b076b1ab8675027641e98605548a'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url, limit=256 * 1024 * 1024):
    if not url.startswith('https://'):
        raise ValueError('Source acquisition requires HTTPS')
    request = urllib.request.Request(url, headers={'User-Agent': 'Lain42-source-attribution'})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Source exceeds reviewed download budget')
    return data


def original_notices(archive):
    notices = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:*') as source:
        for item in source:
            if item.isfile() and item.size <= 512 * 1024 and Path(item.name).name.upper().startswith(
                    ('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'COPYRIGHT')):
                data = source.extractfile(item).read()
                notices[item.name] = {'sha256': sha(data), 'text': data.decode('utf-8', errors='replace')}
    if not notices:
        # nv-codec-headers preserves complete MIT notices per header, rather
        # than in a file called LICENSE. Retain the entire original header;
        # a SPDX tag or a copyright line alone does not prove permission.
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:*') as source:
            for item in source:
                if not item.isfile() or item.size > 512 * 1024 or Path(item.name).suffix != '.h':
                    continue
                data = source.extractfile(item).read()
                # Formatting and C comment prefixes can wrap the full notice.
                # Normalize only for validation; stored text/hash remain raw.
                normalized = re.sub(rb'[\s*]+', b' ', data)
                if (b'Permission is hereby granted' in normalized and b'THE SOFTWARE IS PROVIDED' in normalized
                        and b'Copyright' in normalized and b'OTHER DEALINGS IN THE SOFTWARE' in normalized):
                    notices[item.name] = {'sha256': sha(data), 'text': data.decode('utf-8'),
                                          'original_notice_location': 'Full MIT notice embedded in original header'}
    if not notices:
        raise ValueError('Original source archive has no full notices')
    return notices


def av_library_metadata():
    # In pinned PyAV 16 this dictionary lives in _core; av.__init__ exports
    # library_versions but not library_meta. Do not fabricate empty metadata.
    from av._core import library_meta
    required = {'libavutil', 'libavcodec', 'libavformat', 'libavdevice',
                'libavfilter', 'libswscale', 'libswresample'}
    if not required <= library_meta.keys() or any(
            not {'version', 'configuration', 'license'} <= record.keys() for record in library_meta.values()):
        raise ValueError('Actual PyAV native metadata is incomplete')
    return library_meta

def pyav_sources():
    import av
    if av.__version__ != '16.0.1':
        raise ValueError('Audit recipe only covers the pinned PyAV 16.0.1')
    version = av.ffmpeg_version_info
    if isinstance(version, bytes):
        version = version.decode('utf-8')
    if version.lstrip('n').split('-')[0] != '8.0':
        raise ValueError('PyAV loaded a different media source version: ' + version)
    folder = OUT / 'pyav-ffmpeg'
    folder.mkdir(parents=True)
    url = f'https://raw.githubusercontent.com/PyAV-Org/pyav-ffmpeg/{BUILDER}/scripts/build-ffmpeg.py'
    script = fetch(url, 256 * 1024)
    if sha(script) != BUILDER_SCRIPT_SHA:
        raise ValueError('Exact PyAV media builder changed')
    builder_url = f'https://codeload.github.com/PyAV-Org/pyav-ffmpeg/tar.gz/{BUILDER}'
    builder = fetch(builder_url)
    # No declared license in this fixed helper: retain factual source identity,
    # never copied helper code or invented redistribution permission.
    builder_rights = {'source_url': builder_url, 'source_sha256': sha(builder),
                      'script_source_url': url, 'script_sha256': sha(script),
                      'original_code_redistributed': False,
                      'status': 'No declared license at the fixed upstream tree',
                      'independent_licensed_rebuild_recipe_required': True}
    try:
        original_notices(builder)
    except ValueError:
        pass
    else:
        raise ValueError('Builder licensing changed; review the original notice')
    packages = []
    # Parse literals only. Never execute an upstream builder just to enumerate
    # its source table. Exclude the commercial-only nonfree FDK configuration.
    for node in ast.walk(ast.parse(script)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'Package':
            continue
        fields = {key.arg: key.value.value for key in node.keywords if isinstance(key.value, ast.Constant)}
        when = next((key.value for key in node.keywords if key.arg == 'when'), None)
        if isinstance(when, ast.Attribute) and when.attr == 'commercial_only':
            continue
        if not {'name', 'source_url', 'sha256'} <= fields.keys():
            raise ValueError('Unreviewed dynamic source entry in fixed builder')
        name, source_url, digest = (fields[k] for k in ('name', 'source_url', 'sha256'))
        if not re.fullmatch('[A-Za-z0-9_-]+', name) or not re.fullmatch('[a-f0-9]{64}', digest):
            raise ValueError('Invalid fixed media dependency identity')
        source_url = source_url.replace('http://', 'https://', 1)
        print('Preserving source and original notices: ' + name, flush=True)
        archive = fetch(source_url)
        if sha(archive) != digest:
            raise ValueError('Corresponding source differs: ' + name)
        filename = name + '-' + digest[:12] + '.source.tar'
        (folder / filename).write_bytes(archive)
        packages.append({'name': name, 'url': source_url, 'sha256': digest, 'bytes': len(archive),
                         'file': filename, 'original_notices': original_notices(archive)})
    if not {'ffmpeg', 'x264', 'x265'} <= {p['name'] for p in packages}:
        raise ValueError('Incomplete community media corresponding sources')
    runtime = {}
    for name, record in av_library_metadata().items():
        def text(value):
            return value.decode('utf-8') if isinstance(value, bytes) else value
        runtime[name] = {key: text(value) for key, value in record.items()}
        if '--enable-nonfree' in runtime[name]['configuration']:
            raise ValueError('PyAV loaded nonfree media outside this source recipe')
    receipt = {'pyav': av.__version__, 'ffmpeg_runtime_version': version, 'library_meta': runtime,
               'builder_commit': BUILDER, 'builder_rights': builder_rights,
               'dependency_sources': packages,
               'source_profile': 'Superset of community source dependencies; no nonfree FDK archive',
               'source_table_not_executed': True}
    (folder / 'sources.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return receipt


def dependency_notices():
    records, binaries = [], {}
    for distribution in importlib.metadata.distributions():
        texts = {}
        identity = {'name': distribution.metadata['Name'], 'version': distribution.version}
        for item in distribution.files or []:
            file = Path(distribution.locate_file(item))
            if not file.is_file():
                continue
            if file.suffix.lower() in {'.dll', '.pyd', '.so', '.dylib'} or '.so.' in file.name:
                binaries.setdefault(sha(file.read_bytes()), []).append(dict(identity, source_path=str(item)))
            if Path(str(item)).name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'COPYRIGHT')) and file.stat().st_size <= 512 * 1024:
                data = file.read_bytes()
                texts[str(item)] = {'sha256': sha(data), 'text': data.decode('utf-8', errors='replace')}
        records.append(dict(identity, ecosystem='Installed Python distribution (includes packaging tools)',
            license=distribution.metadata.get('License-Expression') or distribution.metadata.get('License'),
            original_notices=texts))
    ui = Path('ui').resolve()
    npm = 'npm.cmd' if os.name == 'nt' else 'npm'
    paths = subprocess.check_output([npm, 'ls', '--omit=dev', '--all', '--parseable'], cwd=ui,
                                   text=True, encoding='utf-8')
    for name in paths.splitlines():
        directory = Path(name)
        if directory.resolve() == ui:
            continue
        package = json.loads((directory / 'package.json').read_text(encoding='utf-8'))
        notices = {}
        for file in directory.iterdir():
            if file.is_file() and file.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE')):
                data = file.read_bytes()
                if len(data) > 512 * 1024:
                    raise ValueError('Unexpectedly large original frontend notice')
                notices[file.name] = {'sha256': sha(data), 'text': data.decode('utf-8', errors='replace')}
        records.append({'ecosystem': 'Bundled frontend dependency', 'name': package['name'],
                        'version': package['version'], 'license': package.get('license'), 'original_notices': notices})
    for name, path in [('Original application', Path('../LICENSE')), ('Shared MIT source', Path('SHARED-SOURCE-LICENSE')),
                       ('shadcn/ui', ui / 'src/components/ui/LICENSE.md')]:
        data = path.read_bytes()
        records.append({'ecosystem': 'Original source', 'name': name,
                        'original_notices': {str(path): {'sha256': sha(data), 'text': data.decode('utf-8')}}})
    python_version = '.'.join(str(v) for v in sys.version_info[:3])
    openssl_version = ssl.OPENSSL_VERSION.split()[1]
    for name, version, url in [
        ('CPython', python_version, f'https://raw.githubusercontent.com/python/cpython/v{python_version}/LICENSE'),
        ('OpenSSL', openssl_version, f'https://raw.githubusercontent.com/openssl/openssl/openssl-{openssl_version}/LICENSE.txt')]:
        data = fetch(url, 512 * 1024)
        if len(data) < 100:
            raise ValueError('Incomplete runtime original notice')
        records.append({'ecosystem': 'Bundled native runtime', 'name': name, 'version': version, 'source': url,
                        'original_notices': {'LICENSE': {'sha256': sha(data), 'text': data.decode('utf-8')}}})
    return records, binaries


def main():
    if not (ROOT / '_internal/bin/subtitle-engine').is_dir():
        raise ValueError('Need actual original frozen worker before auditing')
    OUT.mkdir(exist_ok=True)
    notices, binary_sources = dependency_notices()
    pyav = pyav_sources()
    native, unresolved = [], []
    sdk = json.loads(Path('packaging/webview2-sdk.json').read_text(encoding='utf-8'))
    sdk_hashes = {record['sha256'] for record in sdk['files']}
    for file in ROOT.rglob('*'):
        if not file.is_file() or (file.suffix.lower() not in {'.dll', '.pyd', '.so', '.dylib'} and '.so.' not in file.name):
            continue
        digest = sha(file.read_bytes())
        record = {'path': file.relative_to(ROOT).as_posix(), 'sha256': digest, 'size': file.stat().st_size,
                  'installed_distribution_matches': binary_sources.get(digest, [])}
        if digest in sdk_hashes:
            record['sdk'] = {'name': sdk['name'], 'version': sdk['version'], 'original_notice': 'MICROSOFT-WEBVIEW2-LICENSE.txt'}
        elif not record['installed_distribution_matches']:
            # Do not label CPython's dependent runtime DLLs, system ELF copies
            # or repaired media libraries licensed merely because they load.
            unresolved.append(record['path'])
        native.append(record)
    subprocess.run(['git', 'archive', '--format=tar.gz', '--output=' + str(OUT / 'application-source.tar.gz'), 'HEAD'], cwd='..', check=True)
    shutil.copyfile('SOURCES.md', ROOT / 'SOURCES.md')
    report = {'commit': os.environ['GITHUB_SHA'], 'dependency_notices': notices,
              'pyav_media_source_archive_count': len(pyav['dependency_sources']), 'native_files': native,
              'unresolved_native_runtime_files': unresolved, 'redistribution_audit_complete': False,
              'source_archive_sha256': sha((OUT / 'application-source.tar.gz').read_bytes()),
              'remaining_gate': 'Independent verification of all runtime notices/provenance; no public release yet'}
    (OUT / 'native-attribution.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    Path('evidence/native-attribution.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'native_files': len(native), 'unresolved': len(unresolved),
                      'pyav_source_archives': report['pyav_media_source_archive_count'], 'release_approved': False}))


if __name__ == '__main__':
    main()
