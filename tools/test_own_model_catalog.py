#!/usr/bin/env python3
"""Metadata-only Apple/Java catalog checks; --live reads public ModelScope metadata."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--json-jar', required=True, type=Path, help='Existing org.json JVM jar (not Android stub jar)')
    p.add_argument('--live', action='store_true')
    a = p.parse_args()
    jar = a.json_jar.resolve()
    if not jar.is_file():
        p.error('org.json jar missing; this script never downloads dependencies')
    with tempfile.TemporaryDirectory(prefix='ortts-catalog-') as tmp:
        out = Path(tmp)
        java = ROOT / 'android/app/src/main/java/com/orient/ortts/demo'
        def run(*args):
            subprocess.run([str(x) for x in args], cwd=ROOT, check=True)
        run('clang', '-fobjc-arc', '-I', ROOT/'apple', ROOT/'tests/apple_own_model_catalog.m', ROOT/'apple/OwnModelCatalog.m', '-framework', 'Foundation', '-o', out/'apple-test')
        run('javac', '-cp', jar, '-d', out, java/'OwnModelCatalog.java', java/'DownloadSelection.java', java/'VerifiedAssetReuse.java', ROOT/'tests/OwnModelCatalogTest.java', ROOT/'tests/VerifiedAssetReuseTest.java')
        run('clang', '-fobjc-arc', '-I', ROOT/'apple', ROOT/'tests/apple_shared_model_files.m', ROOT/'apple/SharedModelFiles.m', '-framework', 'Foundation', '-o', out/'reuse-test')
        run(out/'reuse-test')
        run('java', '-cp', f'{out}:{jar}', 'com.orient.ortts.demo.VerifiedAssetReuseTest')
        fixtures = ROOT/'tests/fixtures/own-model-catalog'
        run(out/'apple-test', fixtures, *([out/'apple.json'] if a.live else []))
        run('java', '-cp', f'{out}:{jar}', 'com.orient.ortts.demo.OwnModelCatalogTest', fixtures, *([out/'java.json'] if a.live else []))
        if a.live:
            apple = {x['manifest_sha256']: x for x in json.loads((out/'apple.json').read_text())}
            android = {x['manifest_sha256']: x for x in json.loads((out/'java.json').read_text())}
            assert apple.keys() == android.keys(), 'Different published manifests'
            for sha in apple:
                for key in ('id', 'revision', 'supported_variants', 'voices', 'decoder', 'p3_only', 'P3_bytes', 'P5_bytes'):
                    assert apple[sha].get(key) == android[sha].get(key), (sha, key)
            print('PASS: cross-client live catalog parity')

if __name__ == '__main__':
    main()
