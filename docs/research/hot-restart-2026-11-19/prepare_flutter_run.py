"""Assemble source-built SDK artifacts for the regular flutter run command."""
import json
import shutil
import subprocess
from pathlib import Path

root = Path.cwd() / '.dart_tool/hot-restart-analysis'
flutter = root / 'flutter'
dart = root / 'dart-sdk'
packages = '/Users/leonmoll/development/flutter/engine/src/flutter/lib/web_ui/.dart_tool/package_config.json'
prebuilt = flutter / 'engine/src/flutter/prebuilts/macos-arm64'
prebuilt.mkdir(parents=True, exist_ok=True)
if not (prebuilt / 'dart-sdk').exists():
    (prebuilt / 'dart-sdk').symlink_to(dart, target_is_directory=True)
# The tool selects macos-x64 on some revisions, even for an arm64 SDK.
x64 = prebuilt.parent / 'macos-x64'
if not x64.exists():
    x64.symlink_to(prebuilt, target_is_directory=True)

for condition in ['baseline', 'context', 'listener', 'both']:
    web = root / condition / 'flutter_web_sdk'
    for name in ['canvaskit', 'flutter_js']:
        if not (web / name).exists():
            shutil.copytree(flutter / 'bin/cache/flutter_web_sdk' / name, web / name)
    kernel = web / 'kernel'
    kernel.mkdir(exist_ok=True)
    spec = root / condition / 'compiled/libraries.json'
    libs = json.loads(spec.read_text())['dartdevc']['libraries']
    command = [str(dart / 'bin/dartaotruntime'), str(dart / 'bin/snapshots/kernel_worker_aot.dart.snapshot'),
               '--target=ddc', '--summary-only', '--include-unsupported-platform-library-stubs',
               f'--packages-file={packages}', f'--libraries-file={spec}',
               f'--output={kernel}/ddc_outline.dill', '--source=dart:core']
    command += [f'--source=dart:{name}' for name in libs]
    subprocess.run(command, check=True)
    target = kernel / 'ddc/canary'
    target.mkdir(parents=True, exist_ok=True)
    for suffix in ['', '.map']:
        shutil.copyfile(root / condition / 'compiled' / ('dart_sdk.js' + suffix), target / ('dart_sdk.js' + suffix))
    # Local artifact discovery expects an out/<configuration> directory.
    link = flutter / 'engine/src/out' / condition
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to(root / condition, target_is_directory=True)
    print('Ready:', condition, flush=True)
