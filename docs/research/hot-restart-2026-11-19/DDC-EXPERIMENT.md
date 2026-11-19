# Experimental DDC cleanup used in the measurements

The DDC curves use the production changes from Gerrit CL 578301, patchset 3.
They demonstrate removal of a native-metadata retention path, but the same
implementation introduces unhandled exceptions in stale JS-interop callbacks
after hot restart. It is **not merge-ready**.

The recorded Gerrit revision is `a188d8b5b38315e8149ce1c2fe2ab07a5430398b`.
The local tested source commit is `cca4921c970dd56bece3f0ecadf6825e9fc2f090`;
its production source matches patchset 3, with a different commit message.
[ddc-experiment.patch](ddc-experiment.patch) preserves the submitted loader,
runtime and manual regression changes independently of Gerrit's open/closed
status. Build outputs and hashes remain in [build-manifest.json](build-manifest.json).

On the status check during this update, Gerrit reported **ABANDONED**. Restoring
the existing change as **WIP** would retain it for design/review discussion;
that would not resolve the regression or make these curves a supported fix.
No new Gerrit patchset, restore or status change was performed by this update.

The experimental labels mean the same thing whether the change is abandoned
or restored as WIP: these are recorded test results for an unsafe candidate.
The two Flutter PRs remain separately tracked.

Source and findings:

- https://dart-review.googlesource.com/c/sdk/+/578301/3
- https://github.com/dart-lang/sdk/issues/64979
- [Callback reproduction](callback_main.dart), [raw result](stale-callback-results.json).
