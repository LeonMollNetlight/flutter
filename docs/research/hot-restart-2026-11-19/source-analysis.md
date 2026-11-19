# Hot-restart cleanup: upstream source analysis

**Subsequent desktop validation and reference audit:** both Flutter PRs work
independently, with the original DDC runtime/loader. CanvasKit cleanup alone
prevents context accumulation and cadence collapse; listener cleanup alone
removes every retired dispatcher's document click registration. Complete
collection after GC requires removing other retention roots as well. That
measurement condition is not a code or landing dependency. The experimental
Dart implementation introduces stale-callback TypeErrors, including in plain
Dart. See [reference-audit.md](reference-audit.md), [EVIDENCE.md](EVIDENCE.md),
and [stale-callback-results.json](stale-callback-results.json).

Research date: **2026-11-19**. Upstream state is a snapshot from this research session; the detailed Dart status was read at **12:08 UTC**. This report is source inspection and review of existing measurement records; it contains **no new builds, runtime reproductions, benchmarks, SDK changes, or deployments**. The parent task's desktop reproductions are independent and are not assumed to have passed. DartPad conclusions below concern **DartPad Preview's in-browser DDC sandboxes**; they do not establish the artifact versions or execution strategy of a separate legacy hosted DartPad deployment.

## Source conclusions

The three changes address different resources that survive an application restart in the same browser environment:

- **Flutter PR 196786** releases CanvasKit surface resources and cached WebGL contexts, and registers renderer disposal with Flutter's existing hot-restart cleanup mechanism. Its renderer-specific behavior applies to Flutter CanvasKit, including ordinary Flutter web development. [F1] [F1-code] [F-init]
- **Flutter PR 196787** removes the capturing document click listener installed by `EnginePlatformDispatcher`. This is Flutter web engine cleanup shared across renderers, rather than a Dart compiler fix. [F2] [F2-code]
- **Dart CL 578301** resets the outgoing DDC runtime and removes its installed properties from persistent native JavaScript constructors/prototypes before the canary library-bundle loader replaces that runtime. It does not require Flutter and does not change dart2js or dart2wasm. [D1] [D-loader] [D-runtime]

**Normal debug `flutter run -d chrome` hot restart is in scope at the Flutter PR base.** That source explicitly enables DDC canary library bundles by default. DWDS invokes Flutter disassembly and then the same DDC restart APIs changed by the Dart CL. DartPad is another consumer of this machinery, not the only possible consumer. The older local Flutter 3.47.8 checkout has different, conditional loader selection; a statement about every Flutter version using the same loader would be incorrect. [F-compile] [F-runner] [DWDS] [L-flutter-options] [L-flutter-build-info]

**None of the three changes was merged when inspected.** The two Flutter PRs are open drafts; the Dart CL is `NEW`, patch set 3. Consequently this report does not establish that a released SDK or deployed DartPad includes them. [F1-status] [F2-status] [D-status]

### Applicability matrix

“Applies” below means the implementation addresses the relevant code path. It does not mean the amount of retained memory or the improvement has been measured in that environment.

| Environment / operation | PR 196786: CanvasKit | PR 196787: dispatcher listener | CL 578301: DDC native extensions |
| --- | --- | --- | --- |
| Plain Dart web, canary DDC library bundles, restart within the same realm | No Flutter CanvasKit engine | No Flutter dispatcher | **Applies** when the loader discards its old runtime; independent of Flutter. [D-loader] [D-runtime] [D-test] |
| Plain Dart web, legacy AMD/DDC runtime-reusing restart | No Flutter engine | No Flutter engine | **New disposal calls do not apply** to the legacy branch; its existing runtime reset retains extensions for reuse. [D-loader] [D-runtime] |
| Plain Dart web, default `build_web_compilers` builders inspected here | No Flutter engine | No Flutter engine | Conditional: the builder options default `canary`, `web-hot-reload`, and `ddc-library-bundle` to false; opting into library bundles/web hot reload selects the relevant path. Merely saying “DDC” does not identify the loader. [B-options] [B-compiler] |
| Normal Flutter web debug hot restart, `flutter run -d chrome`, at PR base `22e676c…` | **Applies with CanvasKit** | **Applies** | **Applies**: canary library bundles are the default and DWDS reaches the changed APIs. [F-compile] [F-runner] [DWDS] |
| Older local Flutter 3.47.8 debug run | Applies with CanvasKit when disassembly runs | Applies when disassembly runs | Depends on effective options: local source maps hot-reload enablement to canary/DDC bundles, otherwise AMD. Do not infer the effective value from the executable's version alone. [L-flutter-options] [L-flutter-build-info] |
| DartPad Preview, Flutter sandbox Run → Hot Restart | **Applies**: inspected sandbox selects CanvasKit | **Applies**: sandbox invokes `ext.flutter.disassemble` | **Applies**: compiler selects canary/DDC and sandbox calls `dartDevEmbedder.hotRestart()`. [DP-flutter] [DP-compiler] [DP-sandbox] |
| DartPad Preview, console/plain Dart sandbox hot restart | No Flutter renderer | No Flutter dispatcher | **Applies** to its canary DDC restart. [DP-compiler] [DP-sandbox] |
| DartPad host UI deployed using a production compilation | Sandbox scope remains determined by its own engine/compiler assets | Same | A production-built host does not turn DDC-compiled sandbox programs into dart2js/dart2wasm programs. [DP-flutter] [DP-compiler] |
| Plain Dart release JavaScript (`dart compile js` / dart2js) | No Flutter engine | No Flutter engine | **Does not apply**: different compiler/runtime, no DDC replacement hook. [D-files] [D-compile-doc] |
| Normal Flutter dart2js profile/release output | Shared surface disposal/resize cleanup changes can execute with CanvasKit; no normal development hot restart | Removal matters if dispatcher disposal is called; no normal development hot restart | **Does not apply** to the compiled application. [F1-code] [F2-code] [Build-doc] [Hot-doc] |
| Plain Dart dart2wasm release output | No Flutter engine | No Flutter engine | **Does not apply**: no DDC loader/runtime. [D-files] [D-compile-doc] |
| Flutter `--wasm` output using Skwasm | **No CanvasKit surface implementation** | Renderer-independent dispatcher code is shared, but ordinary release hot restart is unavailable | **Does not apply** to dart2wasm output. [F-renderer] [F2-code] [Web-doc] [Hot-doc] |
| A `--wasm` distribution/browser fallback that actually runs CanvasKit | Shared CanvasKit disposal can apply to that selected renderer; no demonstrated release restart benefit | Same shared dispatcher-disposal caveat | Classify the executed application by its actual compiler/runtime; dart2js/dart2wasm fallback output is not DDC. [F-renderer] [F1-code] [Web-doc] |

The standalone `DevCompilerBuilder` constructor has a different default from the builder factories: the factory passes its explicitly parsed `ddcLibraryBundle` option. This matrix uses the factory's option defaults, not that constructor's default in isolation. The first-party webdev documentation also describes the traditional development compiler as AMD-based. [B-options] [B-compiler] [Webdev-doc]

### PR 196786: what the code actually changes

`CanvasKitRenderer.initialize()` adds `registerHotRestartListener(dispose)` after initialization. Flutter's existing `ext.flutter.disassemble` service extension iterates the registered listeners; this makes the real renderer disposal reachable from the established development restart lifecycle. The renderer already caches/reuses the JavaScript CanvasKit instance on the window. Neither the patch nor its regression requires replacing the iframe or reloading that Wasm instance. [F1-renderer] [F-init] [F1-test]

`CkSurface.dispose()` becomes idempotent and uses a shared `_releaseCanvasAndContext()` implementation that:

1. Releases the canvas through its provider, removing the context-loss listener before deliberately losing the context.
2. Disposes the SkSurface, abandons/releases and deletes the GrContext, and clears the Dart references.
3. Where a GL handle exists, loses the browser context if it is not already lost, invokes the new interop binding `CanvasKit.deleteContext(handle)`, and sets the stored GL handle to `-1`.

That cleanup is moved into the common surface class, so both onscreen/offscreen disposal use it, and offscreen canvas replacement continues to use it. The existing disposed-state guard in `onContextLost()` predates this PR; the patch makes cleanup/disposal happen and removes the listener, rather than introducing that guard for the first time. [F1-surface] [F-base-surface]

The added tests check listener removal, actual WebGL loss, repeated disposal, queued/late callbacks, and twelve emulated restarts retaining the same CanvasKit object. They are engine regression tests, not measurements of compositor frame presentation or total browser memory. [F1-test]

**Scope limit:** CanvasKit is a rendering backend, not a synonym for Dart-to-Wasm compilation. CanvasKit's own Wasm/Skia allocation is separate from a Dart application compiled with dart2wasm. This PR does not edit Skwasm. Its shared surface-disposal change also reaches the offscreen resize-replacement path, so “debug-only source change” would be too strong even though hot restart is a development operation. [F-renderer] [F1-code] [Web-doc]

### PR 196787: what the code actually changes

The dispatcher constructor already registers `dispose` as a hot-restart listener and unconditionally installs the navigation-focus handler. Before the patch, the click callback was only a local variable and disposal did not unregister it. The patch stores it as `_navigationFocusListener` and removes the identical callback with the identical capturing flag (`true.toJS`) in `dispose()`. This does not depend on CanvasKit or on assistive technology actually generating a click: registration creates the reference path. [F2-code] [F-base-dispatcher]

The added regression records registrations/removals across ten dispatchers and checks callback identity and capture options. Its PR description attributes a strong retainer path from the document listener to the old dispatcher, binding, and application; the prior extracted heap-retainer text corroborates that particular historical investigation. Neither establishes an isolated memory-savings number for this PR. [F2-test] [F2] [L-listener-retainers]

### CL 578301: what the code actually changes

Both `LibraryManager.hotRestartEnd()` and its older `hotRestart()` implementation acquire the outgoing `dart:_runtime`, call `runtime.hotRestart()`, then `runtime.disposeNativeExtensions()`, **before clearing `this.libraries`**. This both resets initialized static fields and removes roots installed on JS objects that survive runtime replacement. The CL does not alter the legacy `dart_library.reload` branch, which already calls its runtime reset and reuses native extensions. [D-loader]

The runtime records keys installed on native constructors and their prototypes using `Reflect.ownKeys` before/after installation. A `WeakMap` holds per-target installed-key sets; the enumerable tracking list holds `WeakRef`s rather than strong target references. Disposal dereferences surviving targets, deletes recorded keys, clears the records, and removes the runtime's global polyfill marker. It deliberately avoids blanket deletion of unrelated JavaScript properties. This is a native-JS metadata cleanup, not a generalized app event-listener cleanup. [D-runtime]

The manual browser regression uses a compiled canary SDK and a synthetic non-Flutter probe entrypoint. It alternates both restart APIs over twelve generations and checks stable native constructor symbol counts, outgoing reset callbacks, other-frame cleanup, preservation of a user symbol, legacy-style runtime reset, and collection of a detached frame. The synthetic entrypoint demonstrates that the mechanism is not Flutter-specific; it is not a measured memory benchmark of a normal compiled plain-Dart web app. The test is a manually invoked `.mjs` reproduction script, not evidence that upstream CI ran and passed it. [D-test]

### Normal Flutter and DartPad call paths

At the Flutter PR base, `kDdcCanaryFeatures = true`; `ddcFrontEndOptions` always includes the DDC library-bundle flags. For debug JavaScript, the resident runner recompiles and invokes the `hotRestart` service through DWDS. The matching DWDS 27.2.1 source invokes `ext.flutter.disassemble` when present, delegates to the embedder's older restart API or to `hotRestartBegin`/`hotRestartEnd`, and reaches the loader code the Dart CL patches. This provides a source-based applicability argument for normal Flutter web development without a DartPad-specific assumption. [F-compile] [F-runner] [F-deps] [DWDS]

The inspected DartPad worker compiler explicitly supplies `--target=dartdevc`, `--dartdevc-module-format=ddc`, and `--dartdevc-canary`. Its sandbox defines `$dartReloadModifiedModules` and calls `dartDevEmbedder.hotRestart()`. The Flutter run-mode wrapper calls engine disassembly synchronously before running the restart callback, configures renderer `canvaskit`, and waits for the new engine/app initialization. Console mode simply runs the restart callback. These are source facts about the local SDK checkout, not an audit of deployed generated assets. [DP-compiler] [DP-sandbox] [DP-flutter]

The frontend's checked-in SDK catalog currently identifies Flutter `3.50.0-0.4.pre` with Dart `3.14.0-315.1.beta`, and a separate plain Dart `3.14.0` SDK. A catalog/version string does not prove that the runtime bytes include any of these still-unmerged patches. The old measurement report identifies an explicitly source-built/overridden runtime, which must not be confused with the catalog's normal upstream artifacts. [DP-catalog] [L-report]

## Dependencies and upstream status

### Integration dependencies

| Dependency | Evidence and implication |
| --- | --- |
| **Hard pairing: patched DDC loader + patched compiled DDC SDK** | The loader unconditionally invokes the new runtime entrypoint. Shipping the new loader with an old `dart_sdk.js` leaves that entrypoint absent; shipping only runtime code with the old loader does not invoke the cleanup. The Gerrit commit explicitly requires the loader/runtime SDK to ship together. Replacing runtime Dart source alone does not update already compiled JS artifacts. [D1] [D-loader] [D-runtime] |
| **Independent cleanup paths** | PR 196787 removes its document listener without either other patch; PR 196786 releases its graphics resources without either other patch. Other roots can prevent GC after either cleanup. Complete collection in the desktop fixture required all three experimental cleanups; the DDC implementation remains unsafe because it introduces a callback regression. See [reference-audit.md](reference-audit.md). [F2] [D1] [L-native-retainers] [L-listener-retainers] |
| **CanvasKit resource cleanup is additional** | PR 196786 handles graphics resources/context-cache entries separately from JS application reachability. It is needed for the demonstrated graphics/context problem, not a prerequisite for the Dart CL to compile. [F1] [D-files] [L-gpu] |
| **Existing resize cleanup from Flutter PR 192769** | PR 196786 refactors the offscreen replacement cleanup already present in its base. PR 192769 is merged (2026-11-09; merge commit `f0add0e1fe9d8229638cbbc92d005c2959d6f19a`), so it is existing source context, not another pending hot-restart fix. A port onto older engine source must account for the different surface implementation. [F-resize-status] [F1-surface] [F-base-surface] |
| **Flutter engine changes must reach the selected compiled web engine** | DartPad setup compiles `flutter_web.js` and its web SDK from selected sources/artifacts. Existing cached Flutter web artifacts will not acquire a Dart-source change automatically. The CanvasKit patch also requires the consumed CanvasKit JS API to export `deleteContext`; the subsequent desktop validation confirmed that API with current CanvasKit prebuilts; upstream presubmits remain separate. [DP-setup] [F1-code] [F1] |
| **Engine disassembly must precede restart** | Flutter/DWDS and inspected DartPad already expose/call `ext.flutter.disassemble`. A custom embedder that skips it will not run the Flutter renderer/dispatcher hot-restart listeners merely by resetting DDC. [F-init] [DWDS] [DP-flutter] |
| **Weak-reference support** | The proposed runtime uses JavaScript `WeakMap` and `WeakRef`. Compatibility must be judged against the browsers supported by the selected development runtime. No browser-compatibility testing was performed in this research task. [D-runtime] |

### Earlier observed upstream state (historical snapshot)

| Change | Immutable source revision | Observed state / outstanding work |
| --- | --- | --- |
| [Flutter 196786](https://github.com/flutter/flutter/pull/196786) | Head `3e25df705b11935d0a4a5750e6b8bc26460877b1`; base `22e676c57e1e6d04c2289a47368ea4093bbc3c18` | Open draft, unmerged; GitHub reports `mergeable_state: dirty`. `cla/google` failed and `Awaiting CICD label` was queued. No submitted reviews were returned. PR says author review, a dedicated issue, current-artifact validation, and presubmits remain pending. [F1-status] [F1-checks] [F1-reviews] [F1] |
| [Flutter 196787](https://github.com/flutter/flutter/pull/196787) | Head `b8bbc80b12474d54da242a2e150c6fd6d8dbde9c`; same base | Open draft, unmerged; GitHub reports `mergeable_state: blocked`. Same failed CLA and queued CI-label check; no submitted reviews returned. Same author/issue/current-artifact/presubmit caveats. [F2-status] [F2-checks] [F2-reviews] [F2] |
| [Dart 578301](https://dart-review.googlesource.com/c/sdk/+/578301) | Patch set 3 `a188d8b5b38315e8149ce1c2fe2ab07a5430398b`; parent `d5c8013054ed51a6cbaea152baf1bd88a12505af` | `NEW`, unmerged. No positive review/CQ votes shown. Code-Review, Code-Owners, and Review-Enforcement submit requirements were unsatisfied. Latest messages concern reviewer routing/removal; they do not contain a technical approval or rejection. Patch set 3 is classified `NO_CODE_CHANGE` (commit-message edit). [D-status] |

The Flutter descriptions report local Chrome/dart2js engine tests using Dart 3.13.7 and older cached CanvasKit artifacts; PR 196787 reports all 39 dispatcher tests passing. These are author-reported local checks, not green current-artifact upstream presubmits, and dart2js compilation of an engine test does not imply supported production hot restart. [F1] [F2] [Hot-doc]

## Local checkouts and prior notes located (read only)

No applicable `AGENTS.md` was found in the target checkout or its ancestors, the Dart SDK roots, the Flutter root, or the inspected source/note subtrees. The sibling [DartPad checkout instructions](/Users/leonmoll/prj/dart-pad/AGENTS.md) were read; they scope ordinary development to `pkgs/dartpad_preview` and reserve changes/pushes for explicit authorization. This assignment explicitly authorizes the single report at this path. No SDK or application files were edited.

The inventory below was obtained from directory inspection, `git rev-parse`, `git branch`, `git worktree list`, and read-only status inspection. Paths and local states are an observation from this research task; they can change independently afterward.

| Location | Observed identity / relevance |
| --- | --- |
| [Target DartPad checkout](/Users/leonmoll/prj/dartpad2/dart-pad) | `main`, HEAD `5cca2db935e83cea98ccbc3eb51757f005c82a91`; inspected frontend catalog here. |
| [Other DartPad checkout](/Users/leonmoll/prj/dart-pad) | `fix/stale-diagnostics`, HEAD `0df6cc72c257fb1764c379786c829da1da8cd192`; has `AGENTS.md` and unrelated existing file-tree edits. |
| [Dart SDK checkout](/Users/leonmoll/prj/sdk) | `dartpad-worker-startup-cancellation`, HEAD `c867fa50fbede5460baacca9717fb2d03aeae68f`; contains `pkg/dartpad`, `pkg/dartpad_worker`, DDC, and DWDS sources. |
| [DDC upstream worktree](/Users/leonmoll/prj/sdk-ddc-hot-restart-upstream) | `review/ddc-native-extensions-upstream`, HEAD `cca4921c970dd56bece3f0ecadf6825e9fc2f090`. Its three changed files were compared in memory with Gerrit patch set 3 and are byte-identical; commit SHA differs. |
| [Additional SDK checkout](/Users/leonmoll/prj/sdk-dartpad-cli-fix.01n76jlj) | `dartpad-flutter-checkout-history`, HEAD `e80cb7e044b35b03ad575f0cc64e03f414e59040`. |
| [Flutter checkout](/Users/leonmoll/development/flutter) | Detached HEAD `737ba8f885dc774b53b442759999a312c9461e4e`; cached version file says Flutter 3.47.8 / Dart 3.13.7. Existing engine hot-restart edits and three separate `dev/` edits are present. This is not the upstream PR base or the old measurements' pinned Flutter revision. [L-flutter-version] [L-report] |
| [SDK source overlay / measurement artifacts](/Users/leonmoll/development/dart-sdk-hot-restart-fix) | Not a complete Git checkout. `baseline/`, `patched/`, generated runtime/regression assets, and the prior report/JSON results remain. [L-report] |
| [DartPad split checkout](/Users/leonmoll/prj/dartpad2/dart-pad-pr-split) | `dartpad-preview-mobile-preview-defaults`, HEAD `db4e2256f9429765391f3e5ece9f930518913366`. |
| [DartPad deployment-fix checkout](/Users/leonmoll/prj/dartpad2/dart-pad-deploy-python-fix) | `dartpad-preview-deploy-python-runtime`, HEAD `858e4988a50c8fcc58bf28a4de245cdf1f75c71a`. |

`git worktree list` also located the earlier DartPad investigation worktree, [t3-2835e8d5](/Users/leonmoll/.t3/worktrees/dart-pad/t3-2835e8d5), HEAD `e54d87fc8bc73e7ae7142dbf18e9fd6a071d42ce`, branch `t3/investigate-mobile-preview-restart`. Its ignored `.dart_tool/mobile-restart-debug` directory contains the historical GPU and heap investigations, extracted retainer paths, raw JSON, and diagnostic logs. The overlay's report points directly to it. [L-report] [L-gpu] [L-native-retainers] [L-listener-retainers]

### Existing measurements: observations, not new results

The prior report is dated **2026-11-09** and pins Flutter `0e4dea427d51a91ccac1f3cbd01bffa927fe6409` with Dart `3.14.0-315.1.beta`. The Flutter PR descriptions explicitly say those measurements have not been revalidated on the upstream ports. [L-report] [F1] [F2]

| Existing record | What was recorded | Attribution / limit |
| --- | --- | --- |
| Desktop Flame workload, mobile UA, LSP off, two warm-up restarts | Post-GC page heap grew **89.1703 MiB over five restarts** before the two application-retention repairs; **1.7907 MiB** with the source-built repairs. [L-desktop-before] [L-desktop-after] | GPU cleanup was already present in both conditions. This compares combined dispatcher/DDC repairs, not each fix in isolation. Page heap excludes compiler-worker heap. [L-report] |
| Samsung CanvasKit/context investigation | Baseline sampled cadence ended at **7 callbacks/s after seven restarts**; GPU-fix run remained **56–60 callbacks/s through thirteen restarts**. Follow-up classified **two active CanvasKit-owned contexts after ten restarts**. [L-gpu] | `requestAnimationFrame` cadence is not compositor presentation. GPU cleanup alone still left post-GC JS heap growth. The harness correction excludes capability-probe contexts from the engine-context count. [L-gpu] [Published-measurements] |
| Samsung initial final weak-tracking patch run | Post-GC page heap grew **40.2133 MiB over fifteen restarts**; JSON explicitly records `passed: false`. [L-phone-initial] | Preserve the failed result. Its higher baseline/initial growth remains unexplained. [L-report] |
| Samsung follow-up on the same iframe/CanvasKit | Post-GC page heap **272.813 → 273.579 MiB**, total **0.7662 MiB over ten restarts**; each observed retired renderer was collected. [L-phone-followup] | A later plateau does not erase or explain the preceding failed run; this is not an independent proof that all mobile memory pressure is fixed. [L-report] |
| Native-extension manual regression | Twelve generations kept native symbol count at six, preserved a user property, and incremented outgoing reset counts. [L-regression] | Regression observation, not a total-memory benchmark or a normal `flutter run`/plain-Dart workload. |

The prior notes also record a large compiler worker and transient memory peaks without forced diagnostic GC. Package-wide Chrome PSS includes other tabs, so it is not solely attributable to the tested application. The cleanup patches do not change the compiler worker or force GC in the product. [L-report] [L-phone-initial] [D-files] [F1-code] [F2-code]

## Unmeasured hypotheses and remaining questions

1. **Plain Dart canary DDC applications should stop accumulating old native-extension generations across hot restart.** The code and non-Flutter regression support the mechanism; retained heap slope, app-object collection, and restart latency for a normally compiled plain-Dart application are unmeasured here. [D-runtime] [D-test]
2. **Normal `flutter run -d chrome` should benefit when its effective loader and engine contain the patches.** The default canary path at the upstream PR base and DWDS lifecycle are established. The old DartPad device/desktop numbers cannot be transferred to this toolchain, a different workload, or the local 3.47.8 build without measurement. [F-compile] [DWDS] [L-report]
3. **Consuming all three changes should remove the three demonstrated categories of restart retention in DartPad Flutter mode.** This predicts the removal of those roots/resources, not elimination of all leaks, GPU problems, or mobile crashes. Single-fix ablations and current-port measurements are still needed for numerical attribution. [F1-code] [F2-code] [D-runtime] [L-report]
4. **The first mobile final-patch run's +40.2 MiB growth is still unexplained.** Potential warm-up, runtime caches, graphics allocations, workload state, and measurement effects have not been distinguished. It must remain an open observation, not be assigned a cause from the later plateau. [L-phone-initial] [L-phone-followup] [L-report]
5. **Release impact needs a separate disposal/resize workload.** Shared CanvasKit cleanup can execute outside development hot restart, but no release dart2js/dart2wasm benefit, regression, or performance result was measured in this task. Skwasm-specific behavior is outside PR 196786's changed source. [F1-surface] [F-renderer] [Hot-doc]
6. **Published artifacts remain to be traced after upstream landing.** A Gerrit merge, Dart SDK build, Flutter artifact consumption, DartPad asset refresh, and deployment are separate events. Which released/deployed bytes contain the cleanup is not established by the source catalog or by current PR state. Loader/runtime pairing and CanvasKit API compatibility must be preserved during any future integration. [D1] [DP-setup] [DP-catalog] [F1]

## Sources

Upstream links below are primary sources. Code is pinned to the inspected PR heads/base or Gerrit revision where practical. API links for status are live and may change after this report.

[F1]: https://github.com/flutter/flutter/pull/196786
[F1-status]: https://api.github.com/repos/flutter/flutter/pulls/196786
[F1-checks]: https://api.github.com/repos/flutter/flutter/commits/3e25df705b11935d0a4a5750e6b8bc26460877b1/check-runs
[F1-reviews]: https://api.github.com/repos/flutter/flutter/pulls/196786/reviews
[F1-code]: https://github.com/flutter/flutter/pull/196786/files
[F1-renderer]: https://github.com/flutter/flutter/blob/3e25df705b11935d0a4a5750e6b8bc26460877b1/engine/src/flutter/lib/web_ui/lib/src/engine/canvaskit/renderer.dart#L60
[F1-surface]: https://github.com/flutter/flutter/blob/3e25df705b11935d0a4a5750e6b8bc26460877b1/engine/src/flutter/lib/web_ui/lib/src/engine/canvaskit/surface.dart#L269
[F1-test]: https://github.com/flutter/flutter/blob/3e25df705b11935d0a4a5750e6b8bc26460877b1/engine/src/flutter/lib/web_ui/test/canvaskit/surface_hot_restart_test.dart
[F2]: https://github.com/flutter/flutter/pull/196787
[F2-status]: https://api.github.com/repos/flutter/flutter/pulls/196787
[F2-checks]: https://api.github.com/repos/flutter/flutter/commits/b8bbc80b12474d54da242a2e150c6fd6d8dbde9c/check-runs
[F2-reviews]: https://api.github.com/repos/flutter/flutter/pulls/196787/reviews
[F2-code]: https://github.com/flutter/flutter/blob/b8bbc80b12474d54da242a2e150c6fd6d8dbde9c/engine/src/flutter/lib/web_ui/lib/src/engine/platform_dispatcher.dart#L106
[F2-test]: https://github.com/flutter/flutter/blob/b8bbc80b12474d54da242a2e150c6fd6d8dbde9c/engine/src/flutter/lib/web_ui/test/engine/platform_dispatcher/platform_dispatcher_test.dart#L60
[F-resize-status]: https://api.github.com/repos/flutter/flutter/pulls/192769
[F-init]: https://github.com/flutter/flutter/blob/22e676c57e1e6d04c2289a47368ea4093bbc3c18/engine/src/flutter/lib/web_ui/lib/src/engine/initialization.dart#L142
[F-base-dispatcher]: https://github.com/flutter/flutter/blob/22e676c57e1e6d04c2289a47368ea4093bbc3c18/engine/src/flutter/lib/web_ui/lib/src/engine/platform_dispatcher.dart#L30
[F-base-surface]: https://github.com/flutter/flutter/blob/22e676c57e1e6d04c2289a47368ea4093bbc3c18/engine/src/flutter/lib/web_ui/lib/src/engine/canvaskit/surface.dart#L105
[F-renderer]: https://github.com/flutter/flutter/blob/22e676c57e1e6d04c2289a47368ea4093bbc3c18/engine/src/flutter/lib/web_ui/lib/src/engine/renderer.dart#L29
[F-compile]: https://github.com/flutter/flutter/blob/22e676c57e1e6d04c2289a47368ea4093bbc3c18/packages/flutter_tools/lib/src/compile.dart#L31
[F-runner]: https://github.com/flutter/flutter/blob/22e676c57e1e6d04c2289a47368ea4093bbc3c18/packages/flutter_tools/lib/src/isolated/resident_web_runner.dart#L433
[F-deps]: https://github.com/flutter/flutter/blob/22e676c57e1e6d04c2289a47368ea4093bbc3c18/packages/flutter_tools/pubspec.yaml#L23
[D1]: https://dart-review.googlesource.com/c/sdk/+/578301/3
[D-status]: https://dart-review.googlesource.com/changes/578301/detail?o=CURRENT_REVISION&o=MESSAGES&o=DETAILED_LABELS&o=SUBMIT_REQUIREMENTS
[D-files]: https://dart-review.googlesource.com/c/sdk/+/578301/3
[D-loader]: https://dart-review.googlesource.com/c/sdk/+/578301/3/pkg/dev_compiler/lib/js/ddc/ddc_module_loader.js
[D-runtime]: https://dart-review.googlesource.com/c/sdk/+/578301/3/sdk/lib/_internal/js_dev_runtime/private/ddc_runtime/classes.dart
[D-test]: https://dart-review.googlesource.com/c/sdk/+/578301/3/pkg/dev_compiler/test/repro/native_extensions_hot_restart.mjs
[DWDS]: https://dart.googlesource.com/sdk/+/d5c8013054ed51a6cbaea152baf1bd88a12505af/pkg/dwds/web/reloader/ddc_library_bundle_restarter.dart
[B-options]: https://github.com/dart-lang/build/blob/754c93454f39945a7efbeea71a4b0caed10f1a19/builder_pkgs/build_web_compilers/lib/builders.dart#L314
[B-compiler]: https://github.com/dart-lang/build/blob/754c93454f39945a7efbeea71a4b0caed10f1a19/builder_pkgs/build_web_compilers/lib/src/dev_compiler_builder.dart#L209
[D-compile-doc]: https://dart.dev/tools/dart-compile
[Webdev-doc]: https://dart.dev/tools/dartdevc
[Web-doc]: https://docs.flutter.dev/platform-integration/web/renderers
[Build-doc]: https://docs.flutter.dev/testing/build-modes
[Hot-doc]: https://docs.flutter.dev/tools/hot-reload
[Published-measurements]: https://github.com/LeonMollNetlight/flutter/blob/dbfe601f0600cb719e5c3de75f7238a0255e215d/docs/review/hot-restart/measurements.json

Local source citations refer to the observed checkout identities listed above. Existing measurement citations refer to retained historical artifacts; none was generated by this research task.

[DP-compiler]: /Users/leonmoll/prj/sdk/pkg/dartpad_worker/lib/src/tools/frontend_server_compiler.dart:255
[DP-sandbox]: /Users/leonmoll/prj/sdk/pkg/dartpad_worker/lib/src/asset/sandbox.js:531
[DP-flutter]: /Users/leonmoll/prj/sdk/pkg/dartpad/asset/sandbox_flutter_patch.js:98
[DP-setup]: /Users/leonmoll/prj/sdk/pkg/dartpad/lib/src/setup/flutter.dart:399
[DP-catalog]: /Users/leonmoll/prj/dartpad2/dart-pad/pkgs/dartpad_preview/dartpad_frontend/lib/sdks.g.dart:12
[L-flutter-version]: /Users/leonmoll/development/flutter/bin/cache/flutter.version.json
[L-flutter-options]: /Users/leonmoll/development/flutter/packages/flutter_tools/lib/src/runner/flutter_command.dart:1412
[L-flutter-build-info]: /Users/leonmoll/development/flutter/packages/flutter_tools/lib/src/build_info.dart:321
[L-report]: /Users/leonmoll/development/dart-sdk-hot-restart-fix/REPORT.txt
[L-native-retainers]: /Users/leonmoll/.t3/worktrees/dart-pad/t3-2835e8d5/.dart_tool/mobile-restart-debug/gc-analysis/retainers-readable.txt
[L-listener-retainers]: /Users/leonmoll/.t3/worktrees/dart-pad/t3-2835e8d5/.dart_tool/mobile-restart-debug/gc-analysis/source-retainers-readable.txt
[L-desktop-before]: /Users/leonmoll/.t3/worktrees/dart-pad/t3-2835e8d5/.dart_tool/mobile-restart-debug/gc-analysis/desktop-memory.json
[L-desktop-after]: /Users/leonmoll/development/dart-sdk-hot-restart-fix/desktop-fixed-memory.json
[L-gpu]: /Users/leonmoll/.t3/worktrees/dart-pad/t3-2835e8d5/.dart_tool/mobile-restart-debug/local-engine-summary.json
[L-phone-initial]: /Users/leonmoll/development/dart-sdk-hot-restart-fix/phone-gc-results.json
[L-phone-followup]: /Users/leonmoll/development/dart-sdk-hot-restart-fix/phone-followup.json
[L-regression]: /Users/leonmoll/development/dart-sdk-hot-restart-fix/regression/native-extensions-regression.json
