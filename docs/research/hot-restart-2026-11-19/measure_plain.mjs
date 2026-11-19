import assert from 'node:assert/strict';
import { connect, gcSample, writeFile } from './cdp.mjs';
import { resolve } from 'node:path';
const root = resolve('.dart_tool/hot-restart-analysis');
const rows = [];
for (let repetition = 1; repetition <= 3; repetition++) {
  for (const condition of repetition % 2 ? ['baseline', 'fixed'] : ['fixed', 'baseline']) {
    const c = await connect();
    try {
      await c.inject(`${root}/plain/${condition}/loader.js`);
      await c.inject(`${root}/plain/${condition}/dart_sdk.js`);
      await c.inject(`${root}/plain/app.js`);
      await c.evaluate(`(() => {
        self.payloads = [];
        self.__publishPayload = value => payloads.push(new WeakRef(value));
        self.$dartReloadModifiedModules = async (files, callback) => { if (typeof callback === 'function') callback(); };
        dartDevEmbedder.runMain('org-dartlang-app:/docs/research/hot-restart-2026-11-19/plain_main.dart', {});
      })()`);
      for (let restart = 0; restart <= 15; restart++) {
        if (restart) await c.evaluate('dartDevEmbedder.hotRestart()');
        const heap = await gcSample(c);
        const state = await c.evaluate(`({symbols: Object.getOwnPropertySymbols(Function).length,
          retainedPayloads: payloads.filter(r => r.deref()).length, generations: payloads.length})`);
        const row = {condition, repetition, restart, ...heap, ...state};
        rows.push(row);
        console.log(JSON.stringify(row));
        if (condition === 'fixed') {
          assert.equal(state.symbols, 6, 'Fixed metadata grew');
          assert.equal(state.retainedPayloads, 1, 'Retired Dart payload survived GC');
        }
      }
    } finally { await c.close(); }
  }
}
await writeFile('docs/research/hot-restart-2026-11-19/plain-results.json', JSON.stringify({
  measuredAt: new Date().toISOString(), workload: 'Compiled plain Dart app, 4 MiB Uint8List per generation',
  gc: 'HeapProfiler.collectGarbage before each sample', repetitions: 3, restarts: 15, rows,
}, null, 2) + '\n');
