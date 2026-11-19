import { readFile, writeFile } from 'node:fs/promises';
export { readFile, writeFile };

export async function connect(port = 9433, targetId) {
  const base = `http://127.0.0.1:${port}`;
  const tab = targetId
    ? (await (await fetch(`${base}/json/list`)).json()).find(t => t.id === targetId)
    : await (await fetch(`${base}/json/new?about:blank`, {method: 'PUT'})).json();
  if (!tab) throw Error('Owned test tab missing');
  const ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0;
  const pending = new Map(), listeners = new Map();
  ws.onmessage = ({data}) => {
    const message = JSON.parse(data);
    if (message.id) {
      const request = pending.get(message.id);
      if (!request) return;
      pending.delete(message.id);
      clearTimeout(request.timer);
      message.error ? request.reject(Error(JSON.stringify(message.error))) : request.resolve(message.result);
    } else for (const callback of listeners.get(message.method) ?? []) callback(message.params);
  };
  function send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++nextId;
      const timer = setTimeout(() => { pending.delete(id); reject(Error(`${method} timeout`)); }, 60000);
      pending.set(id, { resolve, reject, timer });
      ws.send(JSON.stringify({id, method, params}));
    });
  }
  function on(event, callback) {
    if (!listeners.has(event)) listeners.set(event, new Set());
    listeners.get(event).add(callback);
    return () => listeners.get(event).delete(callback);
  }
  async function evaluate(expression) {
    const result = await send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
    if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text);
    return result.result.value;
  }
  async function inject(path) {
    const source = await readFile(path, 'utf8');
    await evaluate(`(() => { const s = document.createElement('script'); s.textContent = ${JSON.stringify(source)}; document.head.append(s); s.remove(); })()`);
  }
  async function close() {
    await fetch(`${base}/json/close/${tab.id}`).catch(() => {});
    ws.close();
  }
  return {tab, send, on, evaluate, inject, close};
}

export async function gcSample(c) {
  // A separate task after dereferencing weak targets, followed by major GC.
  await c.evaluate('new Promise(r => setTimeout(r, 50))');
  await c.send('Runtime.discardConsoleEntries');
  await c.send('HeapProfiler.collectGarbage');
  return c.send('Runtime.getHeapUsage');
}
