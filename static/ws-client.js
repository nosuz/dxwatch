(function () {
  // mode → heartbeat field name for status display
  var HB_FIELD = {
    from_jp: 'last_mqtt_ts_from_jp',
    to_jp: 'last_mqtt_ts_to_jp',
    dxpedition: 'last_mqtt_ts_dxpedition',
  };

  function createWsClient(options) {
    var map = options.map;
    var statusEl = options.statusEl;
    var colorMap = options.colorMap;
    var markerTtl = options.markerTtl || 180000;
    var onUnavailableFn = options.onUnavailable || null;
    var onSlotsFn = options.onSlots || null;

    var markers = [];
    var worker = null;
    var lastHb = null;
    var currentMode = null;
    var currentDxcall = null;

    function clearAll() {
      markers.forEach(function (item) {
        map.removeLayer(item.marker);
      });
      markers = [];
    }

    function cleanupMarkers() {
      var now = Date.now();
      markers = markers.filter(function (item) {
        if (now - item.timestamp > markerTtl) {
          map.removeLayer(item.marker);
          return false;
        }
        return true;
      });
    }

    setInterval(cleanupMarkers, 10000);

    function buildWsUrl(state) {
      var proto = (location.protocol === 'https:') ? 'wss://' : 'ws://';
      var url = proto + location.host + '/ws?mode=' + encodeURIComponent(state.currentMode);
      if (state.local) url += '&local=1';
      if (state.mycall) url += '&mycall=' + encodeURIComponent(state.mycall);
      if (state.dxcall) url += '&dxcall=' + encodeURIComponent(state.dxcall);
      if (state.txrx) url += '&txrx=' + encodeURIComponent(state.txrx);
      return url;
    }

    function plotSpot(data) {
      if (data.mode && currentMode && data.mode !== currentMode) return;
      if (currentMode === 'dxpedition' && currentDxcall && data.dxcall && data.dxcall !== currentDxcall) return;

      var bValue = parseInt((data.b || '').replace('m', ''), 10);
      var color = colorMap[bValue] || 'gray';
      var timestamp = (typeof data.ts === 'number') ? data.ts * 1000 : Date.now();

      var marker = L.circleMarker([data.lat, data.lon], {
        radius: 8,
        color: color,
        fillColor: color,
        fillOpacity: 0.8,
      }).addTo(map);

      markers.push({ marker: marker, timestamp: timestamp });
      cleanupMarkers();
    }

    function ensureWorker() {
      if (worker) return worker;
      console.log('[ws-client] creating worker');
      worker = new Worker('/static/ws-worker.js');
      worker.onerror = function (e) {
        console.error('[ws-client] worker error:', e.message, e);
      };
      worker.onmessage = function (e) {
        var data = e.data;
        if (!data) return;

        if (data.type === 'unavailable') {
          console.log('[ws-client] unavailable: used=' + data.used + ' max=' + data.max);
          if (worker) worker.postMessage({ type: 'stopReconnect' });
          if (onUnavailableFn) onUnavailableFn(data.used, data.max);
          return;
        }

        if (data.type === 'slots') {
          console.log('[ws-client] slots: ' + data.used + '/' + (data.max || '∞'));
          if (onSlotsFn) onSlotsFn(data.used, data.max);
          return;
        }

        if (data.type === 'status') {
          console.log('[ws-client] status:', data.text);
          if (statusEl) statusEl.textContent = 'status: ' + data.text;
          return;
        }

        if (data.type === 'hb') {
          lastHb = data;
          return;
        }

        if (data.type === 'spot') {
          plotSpot(data);
        }
      };
      return worker;
    }

    function connect(state) {
      currentMode = state.currentMode;
      currentDxcall = state.dxcall || null;
      var url = buildWsUrl(state);
      console.log('[ws-client] connect:', url);
      var w = ensureWorker();
      w.postMessage({ type: 'connect', url: url });
    }

    function disconnect() {
      if (worker) {
        console.log('[ws-client] disconnect');
        worker.postMessage({ type: 'disconnect' });
        worker.terminate();
        worker = null;
      }
    }

    function pause() {
      if (worker) {
        console.log('[ws-client] pause');
        worker.postMessage({ type: 'pause' });
      }
    }

    function resume() {
      if (worker) {
        console.log('[ws-client] resume');
        worker.postMessage({ type: 'resume' });
      }
    }

    function startStatusTimer(getModeFn) {
      setInterval(function () {
        if (!statusEl || !lastHb) return;
        var mode = getModeFn ? getModeFn() : currentMode;
        var field = HB_FIELD[mode];
        var mqttTs = field ? lastHb[field] : null;
        if (!mqttTs) return;
        var age = Math.round(lastHb.ts - mqttTs);
        statusEl.textContent = 'status: last spot ' + age + 's ago';
      }, 5000);
    }

    function resetDataAge() {
      lastHb = null;
    }

    return {
      clearAll: clearAll,
      connect: connect,
      disconnect: disconnect,
      pause: pause,
      resume: resume,
      startStatusTimer: startStatusTimer,
      resetDataAge: resetDataAge,
      setMarkerTtl: function (ttl) { markerTtl = ttl; },
    };
  }

  window.PskWsClient = { createWsClient: createWsClient };
})();
