/* Keep the MQTT SharedWorker alive and reconnect MQTT as early as possible */
(function () {
  if (typeof SharedWorker === 'undefined') return;
  try {
    var w = new SharedWorker('/static/mqtt-worker.js');
    w.port.start();
    // If mycall is saved, re-establish the MQTT connection immediately in case
    // the worker restarted during navigation (same-tab page moves)
    var mycall = document.cookie
      .split(';')
      .map(function (c) { return c.trim(); })
      .filter(function (c) { return c.startsWith('pskr_mycall='); })
      .map(function (c) { return c.slice('pskr_mycall='.length).trim().toUpperCase(); })
      [0] || '';
    if (mycall) {
      w.port.postMessage({ type: 'setMycall', mycall: mycall });
    }
  } catch (e) {}
})();
