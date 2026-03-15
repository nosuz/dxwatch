(function () {
  const STORAGE_KEY = 'pskr_mydx_buffer';

  function saveSpotToStorage(spot) {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      let spots = raw ? JSON.parse(raw) : [];
      spots.push(spot);
      const cutoff = Date.now() - 900000;  // prune >15 min
      spots = spots.filter(function (s) { return (s._ts || 0) >= cutoff; });
      if (spots.length > 1000) spots = spots.slice(-1000);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(spots));
    } catch (e) {}
  }

  function loadSpotsFromStorage(mycall, markerTtl) {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const cutoff = Date.now() - markerTtl;
      const call = mycall.toUpperCase();
      return JSON.parse(raw).filter(function (s) {
        if ((s._ts || 0) < cutoff) return false;
        return (s.sc || '').toUpperCase() === call || (s.rc || '').toUpperCase() === call;
      });
    } catch (e) { return []; }
  }

  function maidenheadToLatLon(locator) {
    locator = locator.trim().toUpperCase();
    if (locator.length < 4) throw new Error('locator too short');
    let lon = (locator.charCodeAt(0) - 65) * 20 - 180;
    let lat = (locator.charCodeAt(1) - 65) * 10 - 90;
    lon += parseInt(locator[2]) * 2;
    lat += parseInt(locator[3]);
    let lonSize = 2, latSize = 1;
    if (locator.length >= 6) {
      lon += (locator.charCodeAt(4) - 65) * (5 / 60);
      lat += (locator.charCodeAt(5) - 65) * (2.5 / 60);
      lonSize = 5 / 60;
      latSize = 2.5 / 60;
    }
    lon += lonSize / 2;
    lat += latSize / 2;
    return [lat, lon];
  }

  function applyBlur(lat, lon, locator) {
    if (locator.trim().length === 4) {
      lat += (Math.random() - 0.5);
      lon += (Math.random() - 0.5) * 2;
    }
    return [lat, lon];
  }

  function createMqttClient(options) {
    const map = options.map;
    const statusEl = options.statusEl;
    const colorMap = options.colorMap;
    const markerTtl = options.markerTtl || 180000;

    let worker = null;
    let workerPort = null;
    let markers = [];
    let lastData = 0;
    let currentMycall = '';
    let currentMqttMode = 'both';  // 'tx', 'rx', or 'both'
    // Dedup spots that arrive from both localStorage and worker replay
    const plottedTs = new Set();

    function clearAll() {
      markers.forEach(function (item) { map.removeLayer(item.marker); });
      markers = [];
      plottedTs.clear();
    }

    function cleanupMarkers() {
      const now = Date.now();
      markers = markers.filter(function (item) {
        if (now - item.timestamp > markerTtl) {
          map.removeLayer(item.marker);
          return false;
        }
        return true;
      });
    }

    setInterval(cleanupMarkers, 10000);

    function plotSpot(spot, skipStorage) {
      const sc = (spot.sc || '').toUpperCase();
      const rc = (spot.rc || '').toUpperCase();
      const call = currentMycall.toUpperCase();

      let markerLocator = null;
      if (sc === call && spot.rl && currentMqttMode !== 'rx') {
        markerLocator = spot.rl;  // mycall is sender → plot receiver location
      } else if (rc === call && spot.sl && currentMqttMode !== 'tx') {
        markerLocator = spot.sl;  // mycall is receiver → plot sender location
      } else {
        return;
      }

      const timestamp = (typeof spot._ts === 'number') ? spot._ts : Date.now();

      // Deduplicate: skip if already plotted (e.g. from both storage and worker replay)
      const key = sc + '_' + rc + '_' + timestamp;
      if (plottedTs.has(key)) return;
      plottedTs.add(key);

      let lat, lon;
      try {
        [lat, lon] = maidenheadToLatLon(markerLocator);
        [lat, lon] = applyBlur(lat, lon, markerLocator);
      } catch (e) {
        return;
      }

      lastData = Math.max(lastData, timestamp);

      const bValue = parseInt((spot.b || '').replace('m', ''), 10);
      const color = colorMap[bValue] || 'gray';

      const marker = L.circleMarker([lat, lon], {
        radius: 8,
        color: color,
        fillColor: color,
        fillOpacity: 0.8,
      }).addTo(map);

      markers.push({ marker, timestamp });
      cleanupMarkers();

      if (!skipStorage) saveSpotToStorage(spot);
    }

    function ensureWorker() {
      if (workerPort) return workerPort;
      worker = new SharedWorker('/static/mqtt-worker.js');
      workerPort = worker.port;
      workerPort.onmessage = function (e) {
        const msg = e.data;
        if (!msg) return;
        if (msg.type === 'status') {
          if (statusEl) statusEl.textContent = 'status: ' + msg.text;
        } else if (msg.type === 'spot') {
          plotSpot(msg.spot, false);
        } else if (msg.type === 'replay') {
          (msg.spots || []).forEach(function (s) { plotSpot(s, true); });
        }
      };
      workerPort.start();
      return workerPort;
    }

    function connect(mycall, mode) {
      if (!mycall) return;
      currentMycall = mycall;
      currentMqttMode = mode || 'both';
      clearAll();
      // Plot backlog from localStorage first (survives worker restarts)
      loadSpotsFromStorage(mycall, markerTtl).forEach(function (s) { plotSpot(s, true); });
      const port = ensureWorker();
      port.postMessage({ type: 'setMycall', mycall: mycall });
    }

    function disconnect() {
      currentMycall = '';
      if (workerPort) {
        workerPort.postMessage({ type: 'clearMycall' });
      }
    }

    function startStatusTimer() {
      setInterval(function () {
        if (!statusEl || !workerPort) return;
        const now = Date.now();
        if (now - lastData > 30000) {
          // status is managed by worker messages; only override if stale
        }
      }, 1000);
    }

    return { connect, disconnect, clearAll, startStatusTimer };
  }

  window.PskMqttClient = { createMqttClient };
})();
