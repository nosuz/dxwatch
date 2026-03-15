(function () {
  function createWsClient(options) {
    const map = options.map;
    const statusEl = options.statusEl;
    const colorMap = options.colorMap;
    let markerTtl = options.markerTtl || 180000;

    let markers = [];
    let ws = null;

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

        if (data.type !== 'spot') return;
        if (data.mode && data.mode !== state.currentMode) return;
        if (state.currentMode === 'dxpedition' && state.dxcall && data.dxcall && data.dxcall !== state.dxcall) return;

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

    return {
      clearAll,
      connect,
      disconnect,
      setMarkerTtl: function (ttl) { markerTtl = ttl; },
    };
  }

  window.PskWsClient = { createWsClient };
})();
