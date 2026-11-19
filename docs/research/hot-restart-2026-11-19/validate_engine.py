"""Run submitted regressions red on the base and green on both Flutter fixes.

Only the task-owned Flutter checkout is changed. Keep this separate from
performance measurements so compilation/test load cannot affect cadence.
"""
import json
import os
import subprocess
from pathlib import Path

root = Path.cwd()
build = root / '.dart_tool/hot-restart-analysis'
flutter = build / 'flutter'
source = flutter / 'engine/src/flutter/lib/web_ui'
output = root / 'docs/research/hot-restart-2026-11-19'
files = ['canvaskit/canvaskit_api.dart', 'canvaskit/renderer.dart',
         'canvaskit/surface.dart', 'platform_dispatcher.dart']
env = dict(os.environ, DART_SDK_DIR=str(build / 'dart-sdk'),
           CHROME_EXECUTABLE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
base = '22e676c57e1e6d04c2289a47368ea4093bbc3c18'
context = '3e25df705b11935d0a4a5750e6b8bc26460877b1'
listener = 'b8bbc80b12474d54da242a2e150c6fd6d8dbde9c'
original = {relative: (source / 'lib/src/engine' / relative).read_bytes() for relative in files}
results = []


def install(fixed):
    for relative in files:
        ref = context if fixed and relative.startswith('canvaskit/') else listener if fixed else base
        path = 'engine/src/flutter/lib/web_ui/lib/src/engine/' + relative
        (source / 'lib/src/engine' / relative).write_bytes(
            subprocess.check_output(['git', '-C', str(flutter), 'show', f'{ref}:{path}']))


def test(label, paths):
    command = ['engine/src/flutter/lib/web_ui/dev/felt', 'test', '--compile', '--copy-artifacts', '--run',
               '--browser', 'chrome', '--compiler', 'dart2js', '--renderer', 'canvaskit', *paths]
    log = build / (label + '.log')
    with log.open('w') as file:
        result = subprocess.run(command, cwd=flutter, env=env, stdout=file, stderr=subprocess.STDOUT)
    text = log.read_text()
    results.append({'label': label, 'exitCode': result.returncode, 'log': str(log), 'command': command})
    print(label, result.returncode, text[-1500:], flush=True)
    return result.returncode, text


try:
    install(False)
    code, text = test('engine-red', ['test/canvaskit/surface_hot_restart_test.dart',
                                    'test/engine/platform_dispatcher/platform_dispatcher_test.dart'])
    assert code != 0, 'Submitted regressions unexpectedly passed on the base'
    assert 'Expected:' in text and ('Actual:' in text or '[E]' in text), 'Failure did not reach assertions'
    install(True)
    code, text = test('engine-green', ['test/canvaskit/surface_hot_restart_test.dart',
        'test/canvaskit/surface_test.dart', 'test/ui/surface_context_lost_test.dart',
        'test/canvaskit/renderer_test.dart', 'test/canvaskit/rasterizer_test.dart',
        'test/engine/platform_dispatcher/platform_dispatcher_test.dart'])
    assert code == 0, text[-4000:]
finally:
    for relative, contents in original.items():
        (source / 'lib/src/engine' / relative).write_bytes(contents)
    (output / 'engine-validation.json').write_text(json.dumps(results, indent=2) + '\n')
