import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { connect, writeFile } from './cdp.mjs';
const root = resolve('.dart_tool/hot-restart-analysis');
const rows = [];
for (const condition of ['baseline', 'fixed']) {
  const c = await connect();
  try {
    await c.inject(`${root}/plain/${condition}/loader.js`);
    await c.inject(`${root}/plain/${condition}/dart_sdk.js`);
    await c.inject(`${root}/plain/callback.js`);
    await c.evaluate(`(() => {
      self.numbers = []; self.callbackErrors = [];
      self.__reportNumber = n => numbers.push(n);
      self.addEventListener('error', e => {callbackErrors.push(e.message);e.preventDefault();});
      self.$dartReloadModifiedModules = async (files, callback) => {if (typeof callback === 'function') callback();};
      dartDevEmbedder.runMain('org-dartlang-app:/docs/research/hot-restart-2026-11-19/callback_main.dart', {});
      document.dispatchEvent(new Event('probe'));
    })()`);
    const before = await c.evaluate('({numbers:[...numbers], errors:[...callbackErrors]})');
    assert.deepEqual(before.numbers, [42]);
    assert.deepEqual(before.errors, []);
    await c.evaluate('dartDevEmbedder.hotRestart()');
    await c.evaluate(`numbers.length=0; document.dispatchEvent(new Event('probe')); true`);
    const after = await c.evaluate('({numbers:[...numbers], errors:[...callbackErrors]})');
    rows.push({condition,before,after});
    console.log(JSON.stringify(rows.at(-1)));
  } finally { await c.close(); }
}
await writeFile('docs/research/hot-restart-2026-11-19/stale-callback-results.json', JSON.stringify({
  meaning:'A Dart-installed DOM callback intentionally survives hot restart; compare behavior of old and new callbacks', rows,
}, null, 2) + '\n');
