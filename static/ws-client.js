(function () {
  function createWsClient(options) {
    const map = options.map;
    const statusEl = options.statusEl;
    const colorMap = options.colorMap;
    const markerTtl = options.markerTtl || 180000;

    let markers = [];
    let ws = null;
    let lastHb = 0;
    let lastData = 0;
    let lastMqttTsFrom = 0;
    let lastMqttTsTo = 0;
    let lastMqttTsJq = 0;
    let lastMqttTsDx = 0;

    function clearAll() {
      markers.forEach(function (item) {
        map.removeLayer(item.marker);
      });
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

    function buildWsUrl(state) {
      const proto = (location.protocol === 'https:') ? 'wss://' : 'ws://';
      let url = proto + location.host + '/ws?mode=' + encodeURIComponent(state.currentMode);
      if (state.local) {
        url += '&local=1';
      }
      if (state.mycall) {
        url += '&mycall=' + encodeURIComponent(state.mycall);
      }
      if (state.dxcall) {
        url += '&dxcall=' + encodeURIComponent(state.dxcall);
      }
      return url;
    }

    function connect(state) {
      if (state.requireMycall && !state.mycall) {
        if (statusEl) {
          statusEl.textContent = 'status: enter your callsign';
        }
        return;
      }

      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
      }

      ws = new WebSocket(buildWsUrl(state));

      ws.onopen = function () {
        if (statusEl) statusEl.textContent = 'status: websocket connected';
      };
      ws.onclose = function () {
        if (statusEl) statusEl.textContent = 'status: websocket closed';
      };
      ws.onerror = function () {
        if (statusEl) statusEl.textContent = 'status: websocket error';
      };

      ws.onmessage = function (event) {
        const data = JSON.parse(event.data);

        if (data.type === 'hb') {
          lastHb = Date.now();
          if (typeof data.last_mqtt_ts_from_jp === 'number' && data.last_mqtt_ts_from_jp > 0) {
            lastMqttTsFrom = data.last_mqtt_ts_from_jp * 1000;
          }
          if (typeof data.last_mqtt_ts_to_jp === 'number' && data.last_mqtt_ts_to_jp > 0) {
            lastMqttTsTo = data.last_mqtt_ts_to_jp * 1000;
          }
          if (typeof data.last_mqtt_ts_jq3ikn === 'number' && data.last_mqtt_ts_jq3ikn > 0) {
            lastMqttTsJq = data.last_mqtt_ts_jq3ikn * 1000;
          }
          if (typeof data.last_mqtt_ts_dxpedition === 'number' && data.last_mqtt_ts_dxpedition > 0) {
            lastMqttTsDx = data.last_mqtt_ts_dxpedition * 1000;
          }
          return;
        }

        if (data.type !== 'spot') return;
        if (data.mode && data.mode !== state.currentMode) return;
        if (state.currentMode === 'dxpedition' && state.dxcall && data.dxcall && data.dxcall !== state.dxcall) return;

        lastData = Date.now();

        const bValue = parseInt((data.b || '').replace('m', ''), 10);
        const color = colorMap[bValue] || 'gray';
        const timestamp = (typeof data.ts === 'number') ? data.ts * 1000 : Date.now();

        const marker = L.circleMarker([data.lat, data.lon], {
          radius: 8,
          color: color,
          fillColor: color,
          fillOpacity: 0.8,
        }).addTo(map);

        markers.push({ marker, timestamp });
        cleanupMarkers();
      };
    }

    function disconnect() {
      if (!ws) return;
      try {
        ws.close(1000, 'switch or hidden');
      } catch (error) {
        console.error(error);
      }
      ws = null;
    }

    function startStatusTimer(getCurrentMode) {
      setInterval(function () {
        if (!statusEl) return;
        const now = Date.now();
        const hbStale = (now - lastHb > 30000);
        const mode = getCurrentMode();
        const mqttTs = mode === 'from_jp' ? lastMqttTsFrom
          : mode === 'to_jp' ? lastMqttTsTo
          : mode === 'dxpedition' ? lastMqttTsDx
          : lastMqttTsJq;
        const mqttStale = mqttTs ? (now - mqttTs > 30000) : true;
        const dataStale = (now - lastData > 30000);

        if (hbStale) {
          statusEl.textContent = 'status: websocket down (no heartbeat)';
        } else if (mqttStale) {
          statusEl.textContent = 'status: websocket ok, but no new MQTT data';
        } else if (dataStale) {
          statusEl.textContent = 'status: websocket ok, but no spot messages';
        } else {
          statusEl.textContent = 'status: receiving';
        }
      }, 1000);
    }

    return {
      clearAll,
      connect,
      disconnect,
      startStatusTimer,
      resetDataAge: function () { lastData = 0; },
    };
  }

  window.PskWsClient = { createWsClient };
})();
