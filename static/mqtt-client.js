(function () {
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

    let mqttClient = null;
    let markers = [];
    let lastData = 0;

    function clearAll() {
      markers.forEach(function (item) { map.removeLayer(item.marker); });
      markers = [];
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

    function processMessage(payload, mycall) {
      const data = JSON.parse(payload.toString());
      const sc = (data.sc || '').toUpperCase();
      const rc = (data.rc || '').toUpperCase();
      const call = mycall.toUpperCase();

      let markerLocator = null;
      if (sc === call && data.rl) {
        markerLocator = data.rl;  // mycall is sender → plot receiver location
      } else if (rc === call && data.sl) {
        markerLocator = data.sl;  // mycall is receiver → plot sender location
      } else {
        return;
      }

      let lat, lon;
      try {
        [lat, lon] = maidenheadToLatLon(markerLocator);
        [lat, lon] = applyBlur(lat, lon, markerLocator);
      } catch (e) {
        return;
      }

      lastData = Date.now();
      const bValue = parseInt((data.b || '').replace('m', ''), 10);
      const color = colorMap[bValue] || 'gray';

      const marker = L.circleMarker([lat, lon], {
        radius: 8,
        color: color,
        fillColor: color,
        fillOpacity: 0.8,
      }).addTo(map);

      markers.push({ marker, timestamp: lastData });
      cleanupMarkers();
    }

    function connect(mycall) {
      if (!mycall) return;
      disconnect();
      clearAll();
      if (statusEl) statusEl.textContent = 'status: connecting to MQTT...';

      const c = mqtt.connect('wss://mqtt.pskreporter.info:1886', {
        keepalive: 60,
        reconnectPeriod: 5000,
        clean: true,
      });
      mqttClient = c;

      c.on('connect', function () {
        if (statusEl) statusEl.textContent = 'status: MQTT connected';
        c.subscribe('pskr/filter/v2/+/+/' + mycall + '/#');
        c.subscribe('pskr/filter/v2/+/+/+/' + mycall + '/#');
      });

      c.on('message', function (topic, payload) {
        try {
          processMessage(payload, mycall);
        } catch (e) {
          console.error('MQTT message error:', e);
        }
      });

      c.on('error', function (err) {
        if (statusEl) statusEl.textContent = 'status: MQTT error';
        console.error('MQTT error:', err);
      });

      c.on('close', function () {
        if (statusEl) statusEl.textContent = 'status: MQTT disconnected';
      });
    }

    function disconnect() {
      if (!mqttClient) return;
      try { mqttClient.end(true); } catch (e) {}
      mqttClient = null;
    }

    function startStatusTimer() {
      setInterval(function () {
        if (!statusEl || !mqttClient || !mqttClient.connected) return;
        const now = Date.now();
        if (now - lastData > 30000) {
          statusEl.textContent = 'status: MQTT connected, no recent spots';
        } else {
          statusEl.textContent = 'status: receiving';
        }
      }, 1000);
    }

    return { connect, disconnect, clearAll, startStatusTimer };
  }

  window.PskMqttClient = { createMqttClient };
})();
