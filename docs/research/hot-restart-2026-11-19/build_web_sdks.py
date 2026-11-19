"""Build before/after web SDKs without modifying the user's SDK checkout.

Run from the DartPad repository root. Flutter's SDK rewriter and Dart's DDC
compiler are used directly, following engine/src/flutter/web_sdk/BUILD.gn.
Large build outputs stay in .dart_tool/hot-restart-analysis.
"""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / '.dart_tool/hot-restart-analysis'
FLUTTER = OUT / 'flutter'
SOURCE = FLUTTER / 'engine/src/flutter'
DART_SOURCE = Path('/Users/leonmoll/prj/sdk-ddc-hot-restart-upstream')
PACKAGES = Path('/Users/leonmoll/development/flutter/engine/src/flutter/lib/web_ui/.dart_tool/package_config.json')
DART = OUT / 'dart-sdk'
PR_CONTEXT = '3e25df705b11935d0a4a5750e6b8bc26460877b1'
PR_LISTENER = 'b8bbc80b12474d54da242a2e150c6fd6d8dbde9c'


def run(args, **kwargs):
    print(' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def git_file(repo, ref, path):
    return subprocess.check_output(['git', '-C', str(repo), 'show', f'{ref}:{path}'])


def rewrite(web, name, input_dir, api=None, public=False, exclude=None):
    target = web / 'lib' / ('ui' if name == 'ui' else name if public else '_' + name)
    args = [DART / 'bin/dart', f'--packages={PACKAGES}', SOURCE / 'web_sdk/sdk_rewriter.dart',
            f'--input-dir={input_dir}/', f'--output-dir={target}',
            f'--stamp={web}/{name}.stamp', f'--depfile={web}/{name}.d', f'--build-dir={web}']
    args += ['--ui'] if name == 'ui' else [f'--library-name={name}', f'--api-file={api}']
    if public:
        args += ['--public']
    if exclude:
        args += [f'--exclude-pattern={exclude}']
    run(args)


def compile_sdk(web, sdk, output, flutter=True):
    libraries = json.loads((web / 'libraries.json').read_text())['dartdevc']['libraries'] if flutter else {}
    spec = output.parent / 'libraries.json'
    spec.write_text(json.dumps({'dartdevc': {'include': [{'path': str(sdk / 'lib/libraries.json'), 'target': 'dartdevc'}],
                                           'libraries': {n: {'uri': str(web / v['uri'])} for n, v in libraries.items()}}}))
    run([sdk / 'bin/dart', sdk / 'bin/snapshots/dartdevc.dart.snapshot', '--compile-sdk',
         '--modules=ddc', '--canary', '--no-summarize', '-DFLUTTER_WEB_USE_SKIA=true',
         f'--libraries-file={spec}', f'--packages={PACKAGES}', '-o', output,
         'dart:core', *['dart:' + n for n in libraries]])


def main():
    # Apply exactly the production runtime file from the submitted change.
    fixed_dart = OUT / 'dart-sdk-fixed'
    if not fixed_dart.exists():
        shutil.copytree(DART, fixed_dart)
    runtime = 'sdk/lib/_internal/js_dev_runtime/private/ddc_runtime/classes.dart'
    (fixed_dart / runtime.removeprefix('sdk/')).write_bytes(git_file(DART_SOURCE, 'HEAD', runtime))
    loader = 'pkg/dev_compiler/lib/js/ddc/ddc_module_loader.js'
    for condition, sdk, ref in [('baseline', DART, 'HEAD^'), ('fixed', fixed_dart, 'HEAD')]:
        target = OUT / 'plain' / condition
        target.mkdir(parents=True, exist_ok=True)
        (target / 'loader.js').write_bytes(git_file(DART_SOURCE, ref, loader))
        compile_sdk(None, sdk, target / 'dart_sdk.js', flutter=False)
    run([DART / 'bin/dart', DART / 'bin/snapshots/dartdevc.dart.snapshot',
         '--modules=ddc', '--canary', '--no-summarize', '--module-name=app',
         '-o', OUT / 'plain/app.js', ROOT / 'docs/research/hot-restart-2026-11-19/plain_main.dart'])

    base_ref = subprocess.check_output(['git', '-C', str(FLUTTER), 'rev-parse', PR_LISTENER + '^'], text=True).strip()
    engine_files = ['canvaskit/canvaskit_api.dart', 'canvaskit/renderer.dart', 'canvaskit/surface.dart', 'platform_dispatcher.dart']
    for condition in ['baseline', 'context', 'listener', 'both']:
        web = OUT / condition / 'flutter_web_sdk'
        web.mkdir(parents=True, exist_ok=True)
        for rel in engine_files:
            ref = PR_CONTEXT if condition in ['context', 'both'] and rel.startswith('canvaskit/') else PR_LISTENER if condition in ['listener', 'both'] and rel == 'platform_dispatcher.dart' else base_ref
            path = 'engine/src/flutter/lib/web_ui/lib/src/engine/' + rel
            (FLUTTER / path).write_bytes(git_file(FLUTTER, ref, path))
        lib = SOURCE / 'lib/web_ui/lib'
        rewrite(web, 'ui', lib, exclude=str(lib / 'src'))
        rewrite(web, 'ui_web', lib / 'ui_web/src/ui_web', api=lib / 'ui_web/src/ui_web.dart', public=True)
        rewrite(web, 'engine', lib / 'src/engine', api=lib / 'src/engine.dart', exclude=str(lib / 'src/engine/skwasm'))
        for name in ['skwasm_stub', 'skwasm_impl']:
            rewrite(web, name, lib / 'src/engine/skwasm' / name, api=lib / 'src/engine/skwasm' / (name + '.dart'))
        for name in ['web_test_fonts', 'web_locale_keymap']:
            folder = SOURCE / 'third_party' / name / 'lib'
            rewrite(web, name, folder / name, api=folder / (name + '.dart'))
        shutil.copyfile(SOURCE / 'web_sdk/libraries.json', web / 'libraries.json')
        compiled = OUT / condition / 'compiled'
        compiled.mkdir(exist_ok=True)
        compile_sdk(web, DART, compiled / 'dart_sdk.js')
    for condition in ['baseline', 'context', 'listener', 'both']:
        compile_sdk(OUT / condition / 'flutter_web_sdk', fixed_dart, OUT / condition / 'compiled/dart_sdk_fixed.js')
    manifest = {'flutterBase': base_ref, 'contextPR': PR_CONTEXT, 'listenerPR': PR_LISTENER,
                'dartSource': subprocess.check_output(['git', '-C', str(DART_SOURCE), 'rev-parse', 'HEAD'], text=True).strip(),
                'compilerVersion': (DART / 'version').read_text().strip(),
                'files': {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [*OUT.glob('*/compiled/dart_sdk*.js'), *OUT.glob('plain/*/*.js')]}}
    (ROOT / 'docs/research/hot-restart-2026-11-19/build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
