"""Actions-only, hash-bound retrieval of previously compiled and reviewed media.

Current whole-product tests are still mandatory. This retrieves existing bytes;
it does not turn an earlier component pass into a distributable app approval.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.error
import urllib.request
import zipfile

REPO = 'lilyco-42/subtitle-tool'
PRODUCER = 38356164774
REVIEW = 38359763268
STAMP = '8533f05d0fd2f29756b31335c2a8602d71194fe6'
ARTIFACTS = {
    'linux64': (11793104434, '327a4ee5238b9284d82ed077cabdfc74b8bdddfe939fdb30bafe70a472dea7a7'),
    'win64': (11793763011, 'accaf77e067befdf2842183a9990a04821250e922e9b7767604117ef2856696c'),
}


def api(path):
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + '/' + path,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != REPO:
        raise SystemExit('Acquire media only in this repository Actions')
    target = 'win64' if os.name == 'nt' else 'linux64'
    review = api(f'actions/runs/{REVIEW}')
    if (review['head_repository']['full_name'] != REPO or review['status'] != 'completed'
            or review['conclusion'] != 'success' or review['path'] != '.github/workflows/reviewed-media.yml'):
        raise ValueError('Exact independent reviewed-media workflow must have passed')
    reviewed_jobs = api(f'actions/runs/{REVIEW}/jobs?per_page=100')['jobs']
    verifiers = [j for j in reviewed_jobs if j['name'].startswith('verify-media (')]
    if len(verifiers) != 2 or any(j['conclusion'] != 'success' for j in verifiers):
        raise ValueError('Both independent runtime verifiers must have passed')
    producer = api(f'actions/runs/{PRODUCER}')
    if producer['head_repository']['full_name'] != REPO or producer['path'] != '.github/workflows/reviewed-media.yml':
        raise ValueError('Incorrect producer identity')
    jobs = api(f'actions/runs/{PRODUCER}/jobs?per_page=100')['jobs']
    compiled = [j for j in jobs if j['name'] in {'compile-media (linux64)', 'compile-media (win64)'}]
    if len(compiled) != 2 or any(j['conclusion'] != 'success' for j in compiled):
        raise ValueError('Exact source compile jobs must have passed')
    # Runtime CLI changes do not change the separately compiled media recipe.
    # Such changes are tested again through the whole frozen app below.
    subprocess.run(['git', 'diff', '--exit-code', producer['head_sha'], 'HEAD', '--',
                    'desktop/packaging/media-build.py'], check=True)
    identifier, digest = ARTIFACTS[target]
    item = api(f'actions/artifacts/{identifier}')
    if (item['name'] != f'subtitle-media-{target}-{STAMP}' or item['expired']
            or item['digest'] != 'sha256:' + digest
            or item['workflow_run']['id'] != PRODUCER):
        raise ValueError('Compiled media artifact identity differs')
    request = urllib.request.Request(f'https://api.github.com/repos/{REPO}/actions/artifacts/{identifier}/zip',
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    try:
        urllib.request.build_opener(NoRedirect()).open(request, timeout=45)
        raise ValueError('Artifact redirect expected')
    except urllib.error.HTTPError as error:
        if error.code != 302:
            raise ValueError('Cannot retrieve exact media artifact') from None
        url = error.headers['Location']
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname.endswith('.blob.core.windows.net'):
        raise ValueError('Unexpected artifact origin')
    # Never forward the GitHub bearer credential to the signed blob URL.
    with urllib.request.urlopen(url, timeout=180) as response:
        data = response.read(512 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Outer media artifact digest differs')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.namelist() != [target + '.tar.gz']:
            raise ValueError('Unexpected media artifact contents')
        member = archive.getinfo(target + '.tar.gz')
        if member.file_size > 512 * 1024 * 1024:
            raise ValueError('Media archive exceeds budget')
        tar_bytes = archive.read(member)
    root = Path(__file__).resolve().parents[1] / 'reviewed-media'
    if root.exists():
        raise ValueError('Do not overwrite an existing media acquisition')
    root.mkdir()
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as archive:
        if sum(m.size for m in archive.getmembers()) > 1024 * 1024 * 1024:
            raise ValueError('Expanded media exceeds budget')
        archive.extractall(root, filter='data')
    package = root / target
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest['commit'] != STAMP or manifest['target'] != target
            or manifest['ffmpeg_commit'] != '894da5ca7d742e4429ffb2af534fcda0103ef593'
            or manifest['builder_commit'] != '63ac3265b0789ea16c7b1f8351cd2ad195a28722'):
        raise ValueError('Media source identity differs')
    files = {p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file()}
    if files != set(manifest['files']) | {'manifest.json'}:
        raise ValueError('Complete media file set differs')
    for name, record in manifest['files'].items():
        path = (package / name).resolve()
        if not path.is_relative_to(package.resolve()):
            raise ValueError('Media manifest escapes package')
        content = path.read_bytes()
        if len(content) != record['size'] or hashlib.sha256(content).hexdigest() != record['sha256']:
            raise ValueError('Media member differs: ' + name)
    receipt = {'product_commit': os.environ['GITHUB_SHA'], 'media_artifact_commit': STAMP,
               'producer_run': PRODUCER, 'review_run': REVIEW, 'artifact_id': identifier,
               'artifact_sha256': digest, 'target': target, 'all_files_verified': True,
               'current_frozen_product_verification_required': True}
    (root / 'acquisition.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
