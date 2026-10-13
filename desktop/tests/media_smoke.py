"""Inspect source/binary identity and use that exact FFmpeg through the original CLI."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

if os.environ.get('GITHUB_ACTIONS') != 'true':
    raise SystemExit('Product/media verification only in GitHub Actions')
expected_ffmpeg = '894da5ca7d742e4429ffb2af534fcda0103ef593'
expected_builder = '63ac3265b0789ea16c7b1f8351cd2ad195a28722'
target = 'win64' if os.name == 'nt' else 'linux64'
archive_path = Path(sys.argv[1]).resolve()
repository = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    with tarfile.open(archive_path) as archive:
        archive.extractall(root, filter='data')
    package = root / target
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['commit'] == os.environ['GITHUB_SHA'] and manifest['target'] == target
    assert manifest['ffmpeg_commit'] == expected_ffmpeg and manifest['builder_commit'] == expected_builder
    assert manifest['requires_full_source_distribution'] is True
    files = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}
    assert files == set(manifest['files']) | {'manifest.json'}
    for name, record in manifest['files'].items():
        data = (package / name).read_bytes()
        assert len(data) == record['size'] and hashlib.sha256(data).hexdigest() == record['sha256'], name
    with tarfile.open(package / 'sources/ffmpeg-source.tar.xz') as source:
        source_license = source.extractfile('ffmpeg-8.0.1/COPYING.GPLv3').read()
        assert source_license == (package / 'ffmpeg/LICENSE.txt').read_bytes()
        assert source.getmember('ffmpeg-8.0.1/libavcodec/libx264.c')
    source_licenses = {}
    for name in manifest['dependency_source_archives']:
        with tarfile.open(package / 'sources' / name) as source:
            notices = [m for m in source if m.isfile() and Path(m.name).name.upper().startswith(
                ('LICENSE', 'LICENCE', 'COPYING', 'NOTICE')) and '.git/' not in m.name and m.size < 1024 * 1024]
            assert notices, 'Corresponding source archive has no original license: ' + name
            source_licenses[name] = [m.name for m in notices]
    suffix = '.exe' if os.name == 'nt' else ''
    ffmpeg = package / 'ffmpeg/bin' / ('ffmpeg' + suffix)
    ffprobe = package / 'ffmpeg/bin' / ('ffprobe' + suffix)
    environment = dict(os.environ)
    environment['PATH'] = str(ffmpeg.parent) + os.pathsep + environment.get('PATH', '')

    def run(arguments):
        return subprocess.run(arguments, check=True, capture_output=True, env=environment,
                              cwd=root, timeout=120)

    version = run([str(ffmpeg), '-version']).stdout.decode('utf-8', errors='replace')
    assert version.startswith('ffmpeg version 8.0.1'), version
    for flag in ('--enable-gpl', '--enable-version3', '--enable-libass', '--enable-libx264',
                 '--enable-libdav1d', '--disable-autodetect', '--disable-network'):
        assert flag in version, flag
    original = root / 'own.mp4'
    run([str(ffmpeg), '-nostdin', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=12:d=2',
         '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-c:v', 'libx264',
         '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(original)])
    caption = root / 'own.srt'
    caption.write_text('1\n00:00:00,100 --> 00:00:01,800\nORIGINAL MEDIA SOURCE\n\n', encoding='utf-8')
    for mode in ('soft', 'hard'):
        output = root / (mode + '.mp4')
        run([sys.executable, str(repository / 'subtitle_tool.py'), str(original), '--srt', str(caption),
             '--mode', mode, '--font', 'Arial', '--local-only', '--output', str(output)])
        assert output.is_file() and output.stat().st_size > 1000
        if mode == 'soft':
            text = run([str(ffmpeg), '-nostdin', '-i', str(output), '-map', '0:s:0', '-f', 'srt', '-']).stdout
            assert b'ORIGINAL MEDIA SOURCE' in text
        else:
            def frame(path):
                return run([str(ffmpeg), '-nostdin', '-ss', '1', '-i', str(path), '-frames:v', '1',
                            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']).stdout
            assert len(frame(output)) == 320 * 240 * 3 and frame(output) != frame(original)
    probe = json.loads(run([str(ffprobe), '-v', 'error', '-show_streams', '-of', 'json', str(root / 'soft.mp4')]).stdout)
    assert any(stream['codec_type'] == 'subtitle' for stream in probe['streams'])
    evidence = repository / 'desktop/evidence'
    evidence.mkdir(exist_ok=True)
    (evidence / ('media-' + target + '.json')).write_text(json.dumps({
        'commit': os.environ['GITHUB_SHA'], 'target': target,
        'ffmpeg_commit': expected_ffmpeg, 'builder_commit': expected_builder,
        'full_package_manifest_verified': True, 'exact_gpl_license_matches_source': True,
        'corresponding_dependency_sources_with_notices': source_licenses,
        'original_cli_used_exact_packaged_ffmpeg': True, 'real_soft_subtitle': True,
        'real_burned_pixels': True, 'version_and_configuration': version,
        'standalone_product': False}, indent=2), encoding='utf-8')
