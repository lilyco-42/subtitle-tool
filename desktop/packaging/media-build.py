"""Actions-only cross-build using pinned upstream recipes and captured exact source.

Build the external FFmpeg program; do not relink or reimplement its codecs.
The resulting source bundle is required alongside any future binary distribution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

BUILDER = '63ac3265b0789ea16c7b1f8351cd2ad195a28722'
FFMPEG = '894da5ca7d742e4429ffb2af534fcda0103ef593'
STAGES = [
    '10-mingw-std-threads.sh', '10-mingw.sh', '10-xorg-macros.sh', '15-base.sh',
    '20-libiconv.sh', '20-zlib.sh', '25-fribidi.sh', '25-libxml2.sh',
    '45-fonts/25-freetype.sh', '45-fonts/35-fontconfig.sh',
    '45-fonts/45-harfbuzz.sh', '45-fonts/50-freetype.sh',
    '45-libunibreak.sh', '50-libass.sh', '50-dav1d.sh', '50-x264.sh', 'zz-final.sh',
]


def run(arguments, cwd, env=None):
    return subprocess.run(arguments, cwd=cwd, env=env, check=True)


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != 'lilyco-42/subtitle-tool':
        raise SystemExit('Media builds only in this repository Actions')
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', choices=['linux64', 'win64'], required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    stage = root / 'media-build' / args.target
    stage.mkdir(parents=True, exist_ok=False)
    upstream = stage / 'builder'
    run(['git', 'clone', '--no-checkout', 'https://github.com/BtbN/FFmpeg-Builds.git', str(upstream)], root)
    run(['git', 'checkout', '--detach', BUILDER], upstream)
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upstream, text=True).strip()
    if actual != BUILDER:
        raise ValueError('Builder source differs')
    output = root / 'media-output' / args.target
    sources = output / 'sources'
    sources.mkdir(parents=True, exist_ok=False)
    with (sources / 'upstream-builder.tar').open('wb') as stream:
        subprocess.run(['git', 'archive', '--format=tar', BUILDER], cwd=upstream, stdout=stream, check=True)

    # Reuse unchanged library recipes. Select only external libraries used by the
    # subtitle pipeline, keeping FFmpeg's built-in demuxers/decoders/filters intact.
    original_final = (upstream / 'scripts.d/zz-final.sh').read_text()
    replacement = '''ffbuild_depends() {
    echo libiconv
    echo zlib
    echo fribidi
    echo libxml2
    echo fonts
    echo libunibreak
    echo libass
    echo dav1d
    echo x264
}'''
    changed, count = re.subn(r'ffbuild_depends\(\) \{.*?\n\}', replacement, original_final, count=1, flags=re.S)
    if count != 1:
        raise ValueError('Unexpected upstream dependency selector')
    (upstream / 'scripts.d/zz-final.sh').write_text(changed)
    download = (upstream / 'download.sh').read_text()
    selector = 'for STAGE in scripts.d/*.sh scripts.d/*/*.sh; do'
    if download.count(selector) != 1:
        raise ValueError('Unexpected upstream download loop')
    download = download.replace(selector, 'for STAGE in ' + ' '.join('scripts.d/' + s for s in STAGES) + '; do')
    (upstream / 'download.sh').write_text(download)
    defaults = upstream / 'variants/defaults-gpl.sh'
    defaults.write_text(defaults.read_text().replace('--disable-debug',
        '--disable-debug --disable-autodetect --disable-ffplay --disable-network'))

    build = (upstream / 'build.sh').read_text()
    marker = '    cd ffmpeg\n'
    if build.count(marker) != 1:
        raise ValueError('Unexpected FFmpeg source checkout point')
    build = build.replace(marker, marker + '\n'
        f'    test "\\$(git rev-parse HEAD)" = "{FFMPEG}"\n'
        '    git archive --format=tar --prefix=ffmpeg-8.0.1/ HEAD | xz -T0 > /ffbuild/ffmpeg-source.tar.xz\n')
    # Retain the real configured source/build tree for audit rather than losing it
    # at upstream's final cleanup. This stage starts in a new, fixed owned directory.
    build = build.replace('rm -rf ffbuild', ': # retain owned media-build stage for source audit')
    (upstream / 'build.sh').write_text(build)
    # Both execution and the upstream builder are Actions-only. The local variable
    # selects existing public toolchain images, never publishes to upstream.
    env = dict(os.environ, GITHUB_REPOSITORY='btbn/ffmpeg-builds', QUICKBUILD='1',
               GIT_BRANCH_OVERRIDE='n8.0.1')
    for image in ('base', 'base-' + args.target):
        run(['docker', 'pull', 'ghcr.io/btbn/ffmpeg-builds/' + image + ':latest'], upstream)
    run(['bash', 'makeimage.sh', args.target, 'gpl', '8.0'], upstream, env)
    run(['bash', 'build.sh', args.target, 'gpl', '8.0'], upstream, env)

    package_root = upstream / 'ffbuild/pkgroot'
    packages = list(package_root.iterdir())
    if len(packages) != 1 or not (packages[0] / 'LICENSE.txt').is_file():
        raise ValueError('Missing exact generated media package/license')
    packaged = output / 'ffmpeg'
    shutil.copytree(packages[0], packaged, symlinks=True)
    expected = 'ffmpeg.exe' if args.target == 'win64' else 'ffmpeg'
    if not (packaged / 'bin' / expected).is_file():
        raise ValueError('Original FFmpeg executable missing')
    source = upstream / 'ffbuild/ffmpeg-source.tar.xz'
    shutil.copyfile(source, sources / source.name)
    for file in ('config.log', 'config.mak'):
        shutil.copyfile(upstream / 'ffbuild/ffmpeg/ffbuild' / file, sources / file)
    downloaded = []
    for file in sorted((upstream / '.cache/downloads').iterdir()):
        if file.is_file() and not file.is_symlink():
            shutil.copyfile(file, sources / file.name)
            downloaded.append(file.name)
    if not downloaded:
        raise ValueError('No corresponding dependency sources retained')
    with (sources / 'builder-local.patch').open('wb') as stream:
        subprocess.run(['git', 'diff', '--binary'], cwd=upstream, stdout=stream, check=True)
    shutil.copyfile(__file__, sources / 'media-build.py')
    manifest = {'commit': os.environ['GITHUB_SHA'], 'target': args.target,
                'builder_repository': 'https://github.com/BtbN/FFmpeg-Builds', 'builder_commit': BUILDER,
                'ffmpeg_repository': 'https://github.com/FFmpeg/FFmpeg', 'ffmpeg_commit': FFMPEG,
                'ffmpeg_tag': 'n8.0.1', 'dependency_stages': STAGES,
                'dependency_source_archives': downloaded, 'requires_full_source_distribution': True,
                'files': {p.relative_to(output).as_posix(): {'size': p.stat().st_size,
                          'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                          for p in output.rglob('*') if p.is_file()}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    with tarfile.open(output.parent / (args.target + '.tar.gz'), 'w:gz') as archive:
        archive.add(output, arcname=args.target)
    print(json.dumps({'target': args.target, 'source_commit': FFMPEG, 'dependency_archives': len(downloaded),
                      'standalone_product': False}))


if __name__ == '__main__':
    main()
