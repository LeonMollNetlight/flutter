(() => {
  const seen = new WeakSet();
  self.__probe = {contexts: [], clickAdded: 0, clickRemoved: 0, renderers: [], dispatchers: []};
  const add = EventTarget.prototype.addEventListener;
  const remove = EventTarget.prototype.removeEventListener;
  EventTarget.prototype.addEventListener = function(type, callback, options) {
    if (this === document && type === 'click' && (options === true || options?.capture)) __probe.clickAdded++;
    return add.call(this, type, callback, options);
  };
  EventTarget.prototype.removeEventListener = function(type, callback, options) {
    if (this === document && type === 'click' && (options === true || options?.capture)) __probe.clickRemoved++;
    return remove.call(this, type, callback, options);
  };
  for (const name of ['HTMLCanvasElement', 'OffscreenCanvas']) {
    const prototype = self[name]?.prototype;
    if (!prototype) continue;
    const original = prototype.getContext;
    prototype.getContext = function(...args) {
      const context = original.apply(this, args);
      if (context && /webgl/.test(args[0]) && !seen.has(context)) {
        seen.add(context);
        __probe.contexts.push(new WeakRef(context));
      }
      return context;
    };
  }
  self.__sampleCadence = (duration = 1500) => new Promise(resolve => {
    const times = [];
    const start = performance.now();
    let previous;
    function tick(now) {
      if (previous !== undefined) times.push(now - previous);
      previous = now;
      if (now - start < duration) return requestAnimationFrame(tick);
      const sorted = times.toSorted((a, b) => a - b);
      resolve({rafFps: times.length * 1000 / (now - start),
        rafP95Ms: sorted[Math.floor(sorted.length * .95)],
        rafMaxMs: sorted.at(-1), rafIntervals: times});
    }
    requestAnimationFrame(tick);
  });
})()
