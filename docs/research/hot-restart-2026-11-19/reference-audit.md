# Cleanup dependencies and public references

Audited 19 November 2026 against the production diffs and the existing desktop
measurement matrix. No additional SDK build or browser benchmark was needed.

| Problem | Issue | Proposed change | Evidence without the other patches |
| --- | --- | --- | --- |
| Retired CanvasKit surfaces keep contexts and context-loss callbacks | [flutter/flutter#196967](https://github.com/flutter/flutter/issues/196967) | [PR 196786](https://github.com/flutter/flutter/pull/196786) | `baseline` versus `context`: active contexts 16 versus 2; final cadence 9.41 versus 59.93 rAF calls/s |
| Dispatcher disposal leaves its document click listener registered | [flutter/flutter#196968](https://github.com/flutter/flutter/issues/196968) | [PR 196787](https://github.com/flutter/flutter/pull/196787) | `baseline` versus `listener`: 16 add calls in both, 0 versus 15 remove calls; registrations minus removals 16 versus 1 |
| Persistent native JS objects retain outgoing DDC metadata/runtimes | [dart-lang/sdk#64979](https://github.com/dart-lang/sdk/issues/64979) | [Experimental CL 578301/3](https://dart-review.googlesource.com/c/sdk/+/578301/3) | Plain Dart, no Flutter: native `Function` symbols 96 versus 6; the patch also introduces a stale-callback TypeError |

Values above are medians after 15 hot restarts, with three fresh-page runs per
condition. See [raw data](flutter-results.json) and [evidence](EVIDENCE.md).

## Code dependencies

Both Flutter PRs use the existing engine disposal/restart lifecycle. Neither
calls an API introduced by the other PR or by the experimental Dart change.
They can be reviewed and landed independently. CanvasKit PR 196786 uses the
CanvasKit `deleteContext` API, verified with current prebuilts.

The experimental Dart loader calls `disposeNativeExtensions()` from its
rebuilt DDC runtime. Those two Dart artifacts must match if the approach is
ever shipped. This does not require either Flutter PR. The implementation is
not ready to ship because of its callback regression.

## Why the combined GC experiment needs more cleanup

One removed reference does not make an object collectible while another
reference still reaches it. With listener cleanup alone, every old document
listener is removed but all 15 old dispatchers remain reachable through other
paths. The additional comparison `context-ddc` versus `all` removes those
other paths in both conditions: listener removal then changes old-dispatcher
survivors from 15 to 0. This is experimental GC evidence, not a prerequisite
for the listener fix to work.

The experimental Dart cleanup also makes retired CanvasKit callbacks throw.
CanvasKit cleanup prevents that specific callback in the Flutter experiment.
It does not resolve the plain-Dart callback regression. This observation
limits the Dart candidate; it does not make the Flutter graphics fix depend
on Dart cleanup or on dispatcher cleanup.

## Public reference policy applied in this audit

- CanvasKit issue and PR link to each other and to their standalone graphics
  measurements. Unrelated DDC warnings and the unconfirmed older context-loss
  issue #128059 are removed from the issue body.
- Listener issue and PR link to each other and show the standalone listener
  graph. They refer to this evidence report for the separate GC investigation,
  without presenting other patches as prerequisites.
- DDC issue links to the tested experimental patch and to callback-lifecycle
  issue #56127. Its loader/runtime pairing is described as future integration
  work within Dart, and its primary reproduction uses no Flutter.
- Graphics, listener removal, and runtime retention have separate graphs.
  The experimental dispatcher/heap graphs remain supplemental evidence.

The confirmed accumulation measurements use full hot restart. See
[reload-scope.md](reload-scope.md) for the stateful hot-reload distinction.
