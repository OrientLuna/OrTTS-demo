#!/usr/bin/env python3
"""Verify pinned clean upstream submodules, without fetching or changing sources."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def verify():
    lock = json.loads((ROOT / 'vendor/upstream.lock.json').read_text())
    records = []
    for entry in lock['repositories']:
        source = ROOT / entry['path']
        def git(*args):
            return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()
        if not (source / '.git').exists():
            raise ValueError('Initialize pinned submodule: ' + entry['path'])
        if git('rev-parse', 'HEAD') != entry['commit']:
            raise ValueError('Upstream commit mismatch: ' + entry['path'])
        if git('status', '--porcelain', '--untracked-files=normal'):
            raise ValueError('Upstream checkout is modified: ' + entry['path'])
        index = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '--stage', '--', entry['path']], text=True).split()
        if len(index) < 2 or index[0] != '160000' or index[1] != entry['commit']:
            raise ValueError('Gitlink and lock disagree: ' + entry['path'])
        url = subprocess.check_output(['git', '-C', str(ROOT), 'config', '-f', '.gitmodules', '--get', 'submodule.' + entry['path'] + '.url'], text=True).strip()
        if url != entry['url']:
            raise ValueError('Submodule URL and lock disagree: ' + entry['path'])
        records.append({'path': entry['path'], 'commit': entry['commit'], 'clean': True})
    runtime = json.loads((ROOT / 'vendor/runtime.lock.json').read_text())
    sherpa = json.loads((ROOT / 'vendor/sherpa-android.lock.json').read_text())
    commits = {entry['name']: entry['commit'] for entry in lock['repositories']}
    assert commits['audio.cpp'] == runtime['base_commit']
    assert commits['sherpa-onnx'] == sherpa['source_commit']
    assert commits['llama.cpp'] == json.loads((ROOT / 'vendor/unified/lock.json').read_text())['ggml']['commit']
    return records

if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
