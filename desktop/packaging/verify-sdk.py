"""The independent SDK notice must match the official package and all bundled DLLs."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import urllib.request
import zipfile

if os.environ.get('GITHUB_ACTIONS') != 'true' or os.name != 'nt':
    raise SystemExit('SDK verification only in Windows Actions')
pin = json.loads(Path('packaging/webview2-sdk.json').read_text(encoding='utf-8'))
with urllib.request.urlopen(pin['source'], timeout=60) as response:
    package = response.read(40 * 1024 * 1024 + 1)
assert hashlib.sha256(package).hexdigest() == pin['package_sha256']
root = Path('dist/Lain42-Subtitle-Studio')
with zipfile.ZipFile(io.BytesIO(package)) as archive:
    license = archive.read(pin['license_path'])
    assert hashlib.sha256(license).hexdigest() == pin['license_sha256']
    assert Path('MICROSOFT-WEBVIEW2-LICENSE.txt').read_bytes() == license
    for item in pin['files']:
        bundled = root / '_internal/webview/lib' / item['app_path']
        assert hashlib.sha256(archive.read(item['sdk_path'])).hexdigest() == item['sha256']
        assert hashlib.sha256(bundled.read_bytes()).hexdigest() == item['sha256'], item['app_path']
shutil.copyfile('MICROSOFT-WEBVIEW2-LICENSE.txt', root / 'MICROSOFT-WEBVIEW2-LICENSE.txt')
shutil.copyfile('packaging/webview2-sdk.json', root / 'webview2-sdk.json')
Path('evidence/webview2-sdk.json').write_text(json.dumps({'commit': os.environ['GITHUB_SHA'],
    'version': pin['version'], 'official_package_sha256': pin['package_sha256'],
    'full_license_sha256': pin['license_sha256'], 'five_original_bundled_dlls_match': True}), encoding='utf-8')
