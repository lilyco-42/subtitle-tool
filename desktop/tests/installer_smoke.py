"""CI-only install, actual original processing and user-preserving uninstall."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import winreg

if os.environ.get('GITHUB_ACTIONS') != 'true' or os.name != 'nt':
    raise SystemExit('Installation acceptance only on Windows GitHub Actions')
package = Path('dist/Lain42-Subtitle-Studio').resolve()
manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
assert manifest['commit'] == os.environ['GITHUB_SHA']
key_name = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Lain42SubtitleStudio'
with tempfile.TemporaryDirectory(prefix='lain42-subtitle-install-') as temporary:
    root = Path(temporary)
    target = root / 'installed'
    target.mkdir()
    sentinel = target / 'user-owned.txt'
    nested = target / 'personal-exports/keep-video-notes.txt'
    nested.parent.mkdir()
    for item in (sentinel, nested):
        item.write_text('User file, not part of the app', encoding='utf-8')
    setup = Path('dist/lain42-subtitle-studio-windows-setup.exe').resolve()
    subprocess.run([str(setup), '/S', '/D=' + str(target)], check=True, timeout=300)
    for name, digest in manifest['files'].items():
        assert hashlib.sha256((target / name).read_bytes()).hexdigest() == digest, name
    assert (target / 'manifest.json').read_bytes() == (package / 'manifest.json').read_bytes()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name) as key:
        assert Path(winreg.QueryValueEx(key, 'InstallLocation')[0]).resolve() == target.resolve()
    # Preserve the previous portable receipt. The installed test must actually
    # start this installation's worker with host media paths removed.
    shutil.copyfile('evidence/frozen-smoke.json', 'evidence/portable-frozen-smoke.json')
    installed = target / 'Lain42-Subtitle-Studio.exe'
    subprocess.run([sys.executable, 'tests/bundle_smoke.py', str(installed)], check=True, timeout=600)
    receipt = json.loads(Path('evidence/frozen-smoke.json').read_text(encoding='utf-8'))
    assert Path(receipt['app_path']).resolve() == installed.resolve()
    assert Path(receipt['original_engine_path']).is_relative_to(target)
    for flag in ('local_model_cpu_asr', 'edited_soft_track', 'actual_hard_pixels',
                 'real_zip_contents', 'cancelled_actual_running_inference',
                 'clear_private_files', 'no_host_media_path'):
        assert receipt[flag] is True, flag
    shutil.copyfile('evidence/frozen-smoke.json', 'evidence/installed-frozen-smoke.json')
    # NSIS normally exits after launching a temporary copy. A copied executable
    # with _?= waits for actual cleanup instead of treating parent exit as proof.
    uninstaller = root / 'CI-Uninstall.exe'
    shutil.copyfile(target / 'Uninstall.exe', uninstaller)
    subprocess.run([str(uninstaller), '/S', '_?=' + str(target)], check=True, timeout=300)
    assert not (target / 'Uninstall.exe').exists()
    assert not installed.exists()
    for name in list(manifest['files']) + ['manifest.json']:
        assert not (target / name).exists(), 'Leftover app file: ' + name
    for item in (sentinel, nested):
        assert item.read_text(encoding='utf-8') == 'User file, not part of the app'
    start_menu = Path(os.environ['APPDATA']) / 'Microsoft/Windows/Start Menu/Programs/Lain42 字幕工坊'
    assert not start_menu.exists()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name):
            raise AssertionError('Application uninstall registration remains')
    except FileNotFoundError:
        pass
    Path('evidence/installer-acceptance.json').write_text(json.dumps({
        'commit': os.environ['GITHUB_SHA'], 'installed_files_sha256_verified': True,
        'installed_app_real_engine': True, 'installed_offline_asr': True,
        'installed_soft_and_hard_subtitles': True, 'installed_running_cancel': True,
        'uninstall_removed_all_app_files': True, 'unrelated_and_nested_files_preserved': True,
        'start_menu_removed': True, 'registry_removed': True,
        'real_uninstaller_exit_checked': True, 'original_uninstaller_removed': True,
        'redistribution_audit_complete': False}), encoding='utf-8')
