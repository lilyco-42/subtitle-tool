"""Reuse exact already-compiled bytes only when original product source is unchanged.

The previous whole workflow failed in its version-string verifier, not compilation.
New independent tests must pass on both platforms; this does not waive a release gate.
"""
import json
import os
import re
import subprocess
import urllib.request

REPO = 'lilyco-42/subtitle-tool'
SOURCE_RUN = 38356164774


def github(path):
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + '/' + path,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def main():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_REPOSITORY') != REPO:
        raise SystemExit('Media plan only in this repository Actions')
    run = github('actions/runs/' + str(SOURCE_RUN))
    if (run['head_repository']['full_name'] != REPO or run['path'] != '.github/workflows/reviewed-media.yml'
            or run['status'] != 'completed' or not re.fullmatch('[a-f0-9]{40}', run['head_sha'])):
        raise ValueError('Unexpected compiled source identity')
    difference = subprocess.run(['git', 'diff', '--exit-code', run['head_sha'], 'HEAD', '--',
                                 'desktop/packaging/media-build.py', 'subtitle_tool.py'])
    if difference.returncode not in {0, 1}:
        raise ValueError('Could not compare actual producer and current product source')
    jobs = github('actions/runs/' + str(SOURCE_RUN) + '/jobs?per_page=100')['jobs']
    compiled = [job for job in jobs if job['name'] in {'compile-media (linux64)', 'compile-media (win64)'}]
    if len(compiled) != 2 or any(job['status'] != 'completed' or job['conclusion'] != 'success' for job in compiled):
        raise ValueError('Both exact source compilation jobs must have succeeded')
    artifacts = github('actions/runs/' + str(SOURCE_RUN) + '/artifacts?per_page=100')['artifacts']
    selected = [item for item in artifacts if re.fullmatch('subtitle-media-(linux64|win64)-[a-f0-9]{40}', item['name'])]
    if len(selected) != 2:
        raise ValueError('Need exactly both actual media artifacts')
    commits = {item['name'].rsplit('-', 1)[1] for item in selected}
    if len(commits) != 1 or any(not re.fullmatch('sha256:[a-f0-9]{64}', item['digest']) for item in selected):
        raise ValueError('Ambiguous or unhashed compiled artifacts')
    reuse = difference.returncode == 0 and not any(item['expired'] for item in selected)
    # A product-source change or actual expired artifact requires a new compile.
    # A network timeout above is an error, never a reason to start another build.
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write('reuse=' + str(reuse).lower() + '\n')
        output.write('artifact_commit=' + (next(iter(commits)) if reuse else os.environ['GITHUB_SHA']) + '\n')
        output.write('source_run=' + (str(SOURCE_RUN) if reuse else os.environ['GITHUB_RUN_ID']) + '\n')
    print(json.dumps({'reusing_existing_compiled_bytes': reuse, 'producer_head': run['head_sha'],
                      'new_verifier_head': os.environ['GITHUB_SHA'], 'compile_jobs_successful': True,
                      'new_runtime_verification_required': True}))


if __name__ == '__main__':
    main()
