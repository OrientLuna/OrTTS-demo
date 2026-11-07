#!/usr/bin/env python3
"""Screen incremental encoder against offline on local fixtures, no downloads."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import struct


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', type=Path, default=Path('build/moonshine-incremental/moonshine-incremental-probe'))
    p.add_argument('--model', type=Path, default=Path('local/compat/assets/Moonshine-Streaming-GGUF/moonshine-streaming-tiny-q8_0.gguf'))
    p.add_argument('--input', type=Path, default=Path('outputs/unified-2026-11-07/shared-whisper-input.f32'))
    p.add_argument('--out', type=Path, default=Path('outputs/moonshine-incremental-2026-11-07'))
    p.add_argument('--report', type=Path, default=Path('benchmarks/moonshine-incremental-20261107.json'))
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    pcm = a.input.read_bytes()
    # Holdout length/chunk boundaries: repeated speech is a stress fixture, not
    # a natural long-form accuracy corpus. No resampling or new model download.
    long_pcm = ((pcm + bytes(16000*4//2))*7)[:28*16000*4-4*37]
    long_input = a.out/'repeated-28s.f32'; long_input.write_bytes(long_pcm)
    cases = [('short-100ms', a.input, 1600, 'f32'),
             ('short-400ms', a.input, 6400, 'f32'),
             ('short-1000ms', a.input, 16000, 'f32'),
             ('long-irregular', long_input, 7777, 'f32'),
             ('short-f16', a.input, 6400, 'f16'),
             ('long-f16-irregular', long_input, 7777, 'f16'),
             ('short-native-q8', a.input, 6400, 'native')]
    report = {'schema': 1, 'date': '2026-11-07', 'platform': 'macOS ARM64',
              'scope': 'experimental bounded-overlap encoder; decoder restarts each update; no endpoint/cancel ABI',
              'tolerance_relative_l2': 0.0005,
              'model_sha256': digest(a.model), 'binary_sha256': digest(a.binary), 'cases': []}
    report['build_provenance'] = json.loads(a.binary.with_name('provenance.json').read_text())
    for name, fixture, chunk, storage in cases:
        proc = subprocess.run([str(a.binary.resolve()), str(a.model.resolve()), str(fixture.resolve()),
                               str(chunk), storage], capture_output=True, text=True)
        if proc.returncode not in (0, 1):
            raise RuntimeError(f'{name}: {proc.stderr[-2000:]}')
        result = json.loads(proc.stdout)
        result.update(name=name, input_sha256=digest(fixture), exit_code=proc.returncode)
        bound = (result['left_context_frames']+result['right_context_frames']+2)*320+chunk
        result['ring_bound_samples'] = bound
        result['ring_within_bound'] = result['max_ring_samples'] <= bound
        report['cases'].append(result)
        print(name, 'screen_pass=', proc.returncode == 0, 'L2=', result['encoder_relative_l2'],
              'ring=', result['max_ring_samples'], 'final=', result['final_matches_offline'], flush=True)
    report['f32_screen_passed'] = all(c['exit_code']==0 and c['ring_within_bound']
                                    for c in report['cases'] if c['encoder_storage']=='f32')
    report['f16_screen_passed'] = all(c['exit_code']==0 and c['ring_within_bound']
                                    for c in report['cases'] if c['encoder_storage']=='f16')
    report['invalid_input_checks'] = {}
    for name, data in [('nan', struct.pack('<f', float('nan'))*80),
                       ('too_short', bytes(4)), ('unaligned', bytes(321))]:
        fixture = a.out/(name+'.f32'); fixture.write_bytes(data)
        proc = subprocess.run([str(a.binary.resolve()), str(a.model.resolve()), str(fixture.resolve()),
                               '6400', 'f32'], capture_output=True, text=True)
        if proc.returncode != 2:
            raise RuntimeError(f'Invalid input accepted: {name}')
        report['invalid_input_checks'][name] = proc.stderr.strip()
    symbols = subprocess.check_output(['nm', '-g', str(a.binary)], text=True)
    report['ggml_init_definitions'] = sum(' T _ggml_init' in line for line in symbols.splitlines())
    if report['ggml_init_definitions'] != 1:
        raise RuntimeError('Expected one statically linked ggml definition')
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    if not report['f32_screen_passed'] or not report['f16_screen_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
