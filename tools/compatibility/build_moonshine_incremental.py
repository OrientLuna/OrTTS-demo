#!/usr/bin/env python3
"""Build a diagnostic TU against existing OrTTS static libraries; no downloads.

The generated TU reuses the reviewed production position-offset extension and
factors the existing offline greedy decoder into a diagnostic memory-input helper.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=Path('_work/runtime-speech'))
    p.add_argument('--build', type=Path, default=Path('build/speech-incremental-macos'))
    p.add_argument('--out', type=Path, default=Path('build/moonshine-incremental'))
    a = p.parse_args()
    source, build, out = a.source.resolve(), a.build.resolve(), a.out.resolve()
    runtime = source / 'src/models/moonshine_asr/runtime.cpp'
    original = runtime.read_text()
    lock = json.loads((Path(__file__).resolve().parents[2]/'vendor/speech/lock.json').read_text())
    expected = next(f['sha256'] for f in lock['files'] if f['path']=='src/models/moonshine_asr/runtime.cpp')
    if hashlib.sha256(original.encode()).hexdigest() != expected:
        raise SystemExit('Unreviewed Moonshine runtime revision; re-audit transformations first')
    patched = original
    # Production source now includes the reviewed absolute-position extension.
    if 'int64_t position_offset = 0' not in patched or 'p += position_offset' not in patched:
        raise SystemExit('Missing reviewed encoder position-offset extension')
    # Reuse the exact decoder logic from this source, including its token cap.
    start = original.index('    const int64_t audio_max_tokens =', original.index('runtime::TaskResult transcribe_moonshine_asr('))
    end = original.index('    runtime::TaskResult result;\n    result.text_output = runtime::Transcript{decode_moonshine_tokens', start)
    decoder = original[start:end]
    decoder = decoder.replace('        runtime::TaskResult result;\n        result.text_output = runtime::Transcript{"", "en"};\n        return result;', '        return {};')
    helper = '''\nnamespace engine::models::moonshine_asr {
std::string probe_decode_memory(const MoonshineAssets & assets,
    const MoonshineWeights & weights, const engine::core::ExecutionContext & execution_context,
    const std::vector<float> & memory, const MoonshineRuntimeConfig & config) {
    const int64_t memory_frames = memory.size() / assets.config.decoder.hidden_size;
    const std::unordered_map<std::string, std::string> options;
'''+decoder+'''    return decode_moonshine_tokens(assets, decoded);
}
}
'''
    out.mkdir(parents=True, exist_ok=True)
    probe = Path(__file__).with_name('moonshine_incremental_probe.cpp').read_text()
    generated = out / 'probe.cpp'
    generated.write_text(patched + helper + probe)
    binary = out / 'moonshine-incremental-probe'
    audio = build / 'audio'
    libraries = [audio/'libengine_runtime.a', audio/'ggml/src/libggml.a',
                 audio/'ggml/src/libggml-cpu.a', audio/'ggml/src/ggml-blas/libggml-blas.a',
                 audio/'ggml/src/libggml-base.a', audio/'external/sentencepiece/src/libsentencepiece.a',
                 audio/'libcjson_vendor.a', audio/'libyaml_vendor.a']
    command = ['clang++', '-std=c++17', '-O3', '-DNDEBUG',
                    '-I'+str(source/'include'), '-I'+str(source/'external/ggml/include'),
                    str(generated), *(str(x) for x in libraries), '-framework', 'Accelerate',
                    '-o', str(binary)]
    subprocess.run(command, check=True)
    provenance = {'runtime_sha256': expected,
                  'libraries': {str(x.relative_to(build)): hashlib.sha256(x.read_bytes()).hexdigest()
                                for x in libraries},
                  'compiler': subprocess.check_output(['clang++', '--version'], text=True),
                  'flags': ['-std=c++17', '-O3', '-DNDEBUG'],
                  'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    (out/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    print('runtime_sha256='+hashlib.sha256(original.encode()).hexdigest())
    print(binary)


if __name__ == '__main__':
    main()
