"""Compare normal JS/Wasm release output before/after the DDC runtime patch.

This is an applicability control, not a release performance benchmark.
"""
import hashlib
import json
import subprocess
from pathlib import Path

root = Path.cwd() / '.dart_tool/hot-restart-analysis'
fixture = Path('docs/research/hot-restart-2026-11-19/plain_main.dart').resolve()
rows = []
for backend in ['js', 'wasm']:
    for condition, sdk in [('baseline', root / 'dart-sdk'), ('fixed', root / 'dart-sdk-fixed')]:
        output = root / 'release' / backend / condition
        output.mkdir(parents=True, exist_ok=True)
        path = output / ('app.' + backend)
        command = [str(sdk / 'bin/dart'), 'compile', backend, '--no-source-maps']
        if backend == 'js':
            command += ['-O2']
        command += ['-o', str(path), str(fixture)]
        subprocess.run(command, check=True)
        rows.append({'backend': backend, 'condition': condition, 'bytes': path.stat().st_size,
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
result = {'meaning': 'Byte-identical output for this fixture; not a general release performance measurement',
          'rows': rows,
          'identical': {backend: len({r['sha256'] for r in rows if r['backend'] == backend}) == 1
                        for backend in ['js', 'wasm']}}
Path('docs/research/hot-restart-2026-11-19/release-controls.json').write_text(json.dumps(result, indent=2) + '\n')
assert all(result['identical'].values()), result
