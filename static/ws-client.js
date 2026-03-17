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
    var workers = [];
    var lastHb = null;
    var currentMode = null;

    function makeShapeIcon(shape, color) {
      var svg;
      if (shape === 1) {
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18">' +
              '<rect x="1" y="1" width="16" height="16" fill="' + color + '" stroke="#fff" stroke-width="1.5"/></svg>';
      } else if (shape === 2) {
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="20">' +
              '<polygon points="9,1 17,19 1,19" fill="' + color + '" stroke="#fff" stroke-width="1.5"/></svg>';
      } else if (shape === 3) {
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18">' +
              '<polygon points="9,1 17,9 9,17 1,9" fill="' + color + '" stroke="#fff" stroke-width="1.5"/></svg>';
      } else {
        svg = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18">' +
              '<circle cx="9" cy="9" r="7.5" fill="' + color + '" stroke="#fff" stroke-width="1.5"/></svg>';
      }
      return L.divIcon({ html: svg, className: '', iconSize: [18, 18], iconAnchor: [9, 9] });
    }

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

    function plotSpot(data, shape) {
      if (data.mode && currentMode && data.mode !== currentMode) return;

      var bValue = parseInt((data.b || '').replace('m', ''), 10);
      var color = colorMap[bValue] || 'gray';
      var timestamp = (typeof data.ts === 'number') ? data.ts * 1000 : Date.now();

      var marker = L.marker([data.lat, data.lon], { icon: makeShapeIcon(shape, color) }).addTo(map);

      markers.push({ marker: marker, timestamp: timestamp });
      cleanupMarkers();
    }

    function createWorker(shape) {
      var w = new Worker('/static/ws-worker.js');
      w.onerror = function (e) {
        console.error('[ws-client] worker error:', e.message, e);
      };
      w.onmessage = function (e) {
        var data = e.data;
        if (!data) return;

        if (data.type === 'unavailable') {
          console.log('[ws-client] unavailable: used=' + data.used + ' max=' + data.max);
          w.postMessage({ type: 'stopReconnect' });
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
          plotSpot(data, shape);
        }
      };
      return w;
    }

    function connect(state) {
      currentMode = state.currentMode;

      var dxcalls = [];
      if (state.currentMode === 'dxpedition' && state.dxcall) {
        dxcalls = state.dxcall.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
      }

      if (dxcalls.length > 0) {
        dxcalls.forEach(function (cs, i) {
          var url = buildWsUrl({ currentMode: 'dxpedition', dxcall: cs });
          console.log('[ws-client] connect[' + i + ']:', url);
          var w = createWorker(i);
          w.postMessage({ type: 'connect', url: url });
          workers.push(w);
        });
      } else {
        var url = buildWsUrl(state);
        console.log('[ws-client] connect:', url);
        var w = createWorker(0);
        w.postMessage({ type: 'connect', url: url });
        workers.push(w);
      }
    }

    function disconnect() {
      if (workers.length) {
        console.log('[ws-client] disconnect (' + workers.length + ' workers)');
        workers.forEach(function (w) {
          w.postMessage({ type: 'disconnect' });
          w.terminate();
        });
        workers = [];
      }
    }

    function pause() {
      workers.forEach(function (w) { w.postMessage({ type: 'pause' }); });
    }

    function resume() {
      workers.forEach(function (w) { w.postMessage({ type: 'resume' }); });
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
