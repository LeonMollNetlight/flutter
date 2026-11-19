import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { connect, gcSample, readFile, writeFile } from './cdp.mjs';

const root = resolve('.dart_tool/hot-restart-analysis');
const reportPath = resolve('docs/research/hot-restart-2026-11-19/flutter-results.json');
const probe = await readFile('docs/research/hot-restart-2026-11-19/probe.js', 'utf8');
let previous;
try { previous = JSON.parse(await readFile(reportPath, 'utf8')); } catch {}
const rows = previous?.rows ?? [], runs = previous?.runs ?? [];
let commandId = 0;

function launch(condition) {
  const child = spawn(`${root}/flutter/bin/flutter`, [
    `--local-web-sdk=${condition}`, `--local-engine-src-path=${root}/flutter/engine/src`,
    'run', '-d', 'web-server', '--web-port=8879', '--web-hostname=127.0.0.1', '--machine',
  ], {cwd: `${root}/flutter-app`});
  const requests = new Map();
  let buffer = '', log = '', appId;
  let resolveReady, rejectReady;
  const ready = new Promise((r, j) => {resolveReady = r; rejectReady = j;});
  const timeout = setTimeout(() => rejectReady(Error('Flutter launch timeout')), 120000);
  child.stdout.on('data', chunk => {
    log += chunk; buffer += chunk;
    for (;;) {
      const newline = buffer.indexOf('\n');
      if (newline < 0) break;
      const line = buffer.slice(0, newline).trim(); buffer = buffer.slice(newline + 1);
      if (!line.startsWith('[{')) continue;
      let messages;
      try { messages = JSON.parse(line); } catch { continue; }
      for (const message of messages) {
        if (message.event === 'app.start') appId = message.params.appId;
        if (message.event === 'app.started') {clearTimeout(timeout); resolveReady();}
        const request = requests.get(message.id);
        if (request) {requests.delete(message.id); message.error ? request.reject(Error(JSON.stringify(message.error))) : request.resolve(message.result);}
      }
    }
  });
  child.stderr.on('data', chunk => {log += chunk;});
  child.on('exit', code => {clearTimeout(timeout); rejectReady(Error(`Flutter exited ${code}: ${log.slice(-2500)}`));});
  async function restart() {
    const id = ++commandId;
    const response = new Promise((resolve, reject) => requests.set(id, {resolve, reject}));
    child.stdin.write(JSON.stringify([{id, method:'app.restart', params:{appId, fullRestart:true, pause:false}}]) + '\n');
    return response;
  }
  async function stop() {
    child.stdin.end(); child.kill('SIGINT');
    await new Promise(r => {if (child.exitCode !== null) r(); else child.once('exit', r);});
    await writeFile(`${root}/flutter-run-${condition}-measurement.log`, log);
  }
  return {ready, restart, stop};
}

async function save() {
  await writeFile(reportPath, JSON.stringify({measuredAt: new Date().toISOString(),
    workload:'Regular flutter run, CanvasKit animation of 300 circles, 4 MiB payload',
    gc:'HeapProfiler.collectGarbage before each sample', raf:'Main-thread cadence, not compositor presentation', runs, rows}, null, 2) + '\n');
}

const conditions = process.argv.slice(2).length ? process.argv.slice(2) : ['baseline', 'context', 'listener', 'both', 'ddc', 'context-ddc', 'listener-ddc', 'all'];
for (let repetition = 1; repetition <= 3; repetition++) {
  const order = repetition % 2 ? conditions : conditions.toReversed();
  for (const condition of order) {
    if (rows.some(r => r.condition === condition && r.repetition === repetition && r.restart === 15)) continue;
    const sdkCondition = condition === 'all' ? 'both' : condition === 'ddc' ? 'baseline' : condition.replace('-ddc', '');
    const fixedDdc = condition === 'all' || condition === 'ddc' || condition.endsWith('-ddc');
    const runner = launch(sdkCondition);
    let c;
    try {
      await runner.ready;
      c = await connect();
      await c.send('Page.enable');
      await c.send('Page.addScriptToEvaluateOnNewDocument', {source: probe});
      let overrides = 0;
      const errors = [];
      c.on('Runtime.exceptionThrown', e => errors.push(e.exceptionDetails.exception?.description ?? e.exceptionDetails.text));
      await c.send('Runtime.enable');
      if (fixedDdc) {
        const bodies = {
          'dart_sdk.js': (await readFile(`${root}/${sdkCondition}/compiled/dart_sdk_fixed.js`)).toString('base64'),
          'ddc_module_loader.js': (await readFile(`${root}/plain/fixed/loader.js`)).toString('base64'),
        };
        c.on('Fetch.requestPaused', async ({requestId, request}) => {
          const key = request.url.split('/').at(-1);
          await c.send('Fetch.fulfillRequest', {requestId, responseCode:200,
            responseHeaders:[{name:'Content-Type',value:'application/javascript'}], body:bodies[key]});
          overrides++;
        });
        await c.send('Fetch.enable', {patterns:[{urlPattern:'*/dart_sdk.js'},{urlPattern:'*/ddc_module_loader.js'}]});
      }
      await c.send('Page.navigate', {url:'http://127.0.0.1:8879/'});
      await c.send('Page.bringToFront');
      await c.evaluate(`new Promise((resolve, reject) => {
        const start = performance.now();
        const timer = setInterval(() => {
          if (document.querySelector('flutter-view') && self.dartDevEmbedder) {clearInterval(timer); resolve(true);}
          else if (performance.now() - start > 45000) {clearInterval(timer); reject(Error('Flutter startup timeout'));}
        }, 100);
      })`);
      await c.evaluate(`self.__savedCanvasKit = flutterCanvasKit; self.__generation = dartDevEmbedder.hotRestartGeneration ?? 0`);
      const metadata = await c.evaluate(`({ua:navigator.userAgent, width:innerWidth,height:innerHeight,dpr:devicePixelRatio,
        renderer:dartDevEmbedder.importLibrary('dart:_engine').renderer.rendererTag})`);
      runs.push({condition,repetition,metadata,tabId:c.tab.id});
      for (let restart = 0; restart <= 15; restart++) {
        let restartMs = 0;
        if (restart) {
          await c.evaluate(`(() => {
            const engine = dartDevEmbedder.importLibrary('dart:_engine');
            __probe.renderers.push(new WeakRef(engine.renderer));
            __probe.dispatchers.push(new WeakRef(engine.EnginePlatformDispatcher.instance));
          })()`);
          const start = performance.now();
          const result = await runner.restart();
          restartMs = performance.now() - start;
          if (result?.code && result.code !== 0) throw Error(JSON.stringify(result));
          await c.evaluate('new Promise(r => setTimeout(r, 300))');
        }
        const cadence = await c.evaluate('__sampleCadence()');
        const heap = await gcSample(c);
        const state = await c.evaluate(`({
          symbols:Object.getOwnPropertySymbols(Function).length,
          clickAdded:__probe.clickAdded,clickRemoved:__probe.clickRemoved,
          contextsCreated:__probe.contexts.length,
          activeContexts:__probe.contexts.filter(r => { const v=r.deref(); return v && !v.isContextLost(); }).length,
          retiredRenderersAlive:__probe.renderers.filter(r => r.deref()).length,
          retiredDispatchersAlive:__probe.dispatchers.filter(r => r.deref()).length,
          sameCanvasKit:flutterCanvasKit === __savedCanvasKit,
          wasmMemoryBytes:flutterCanvasKit.HEAPU8?.byteLength,
          visible:document.visibilityState,
        })`);
        const row = {condition,repetition,restart,restartMs,...heap,...cadence,...state};
        rows.push(row);
        console.log(JSON.stringify({...row,rafIntervals:undefined}));
        assert(state.sameCanvasKit, 'CanvasKit was replaced');
        if (condition === 'all') {
          assert.equal(state.symbols, rows.find(r=>r.condition===condition&&r.repetition===repetition).symbols);
          assert.equal(state.retiredDispatchersAlive, 0, 'Disposed dispatcher retained');
          assert.equal(state.retiredRenderersAlive, 0, 'Disposed renderer retained');
          assert(state.activeContexts <= 2, 'Retired WebGL contexts remain');
        }
        await save();
      }
      runs.at(-1).errors = errors;
      runs.at(-1).overrides = overrides;
    } finally {if (c) await c.close(); await runner.stop(); await save();}
  }
}
