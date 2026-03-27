(function () {
  'use strict';

  var GLOBAL_BOUNDS = null;
  var JAPAN_BOUNDS  = [[20.0, 122.0], [46.5, 154.0]];

  var VIEWS = {
    '/dx': {
      title: 'DX Watch',
      type: 'ws',
      defaultMode: 'from_jp',
      local: false,
      markerTtl: 180000,
      showModeSelect: true,
      showLimitSlider: true,
      modeOptions: [
        { value: 'from_jp', label: 'JP→World' },
        { value: 'to_jp',   label: 'World→JP' },
      ],
      map: { center: [0, 138], zoom: 3, minZoom: 2, maxBounds: GLOBAL_BOUNDS },
    },
    '/local': {
      title: 'DX Watch: Local',
      type: 'ws',
      defaultMode: 'from_jp',
      local: true,
      markerTtl: 180000,
      label: 'JP↔JP',
      showModeSelect: true,
      showLimitSlider: true,
      modeOptions: [
        { value: 'from_jp', label: 'marker=RL' },
        { value: 'to_jp',   label: 'marker=SL' },
      ],
      map: { center: [36.2, 138.2], zoom: 5, minZoom: 5, maxBounds: JAPAN_BOUNDS },
    },
    '/my_dx': {
      title: 'DX Watch: MyDX',
      type: 'ws',
      defaultMode: 'mydx',
      defaultTxrx: 'tx',
      markerTtl: 900000,
      showModeSelect: true,
      modeOptions: [
        { value: 'tx', label: 'TX (heard me)' },
        { value: 'rx', label: 'RX (I heard)' },
      ],
      showMycall: true,
      map: { center: [0, 138], zoom: 3, minZoom: 2, maxBounds: GLOBAL_BOUNDS },
    },
    '/dxpedition': {
      title: 'DX Watch: DX-pedition',
      type: 'ws',
      defaultMode: 'dxpedition',
      local: false,
      markerTtl: 900000,
      showDxcallSelect: true,
      map: { center: [0, 138], zoom: 3, minZoom: 2, maxBounds: GLOBAL_BOUNDS },
    },
  };

  var map, wsClient, statusEl;
  var currentPath = null;
  var currentMode = 'from_jp';
  var currentTxrx = 'tx';   // tx/rx selector for /my_dx
  var currentDxcall = '';
  var mydxSlotInfo = null;   // { used, max } — last received slots message
  var dxpeditionList = [];   // cache of active dxpeditions from /api/dxpeditions
  var stationMarkers = [];   // L.markers for the DX-pedition station grid location (3 world copies)

  // Background WebSocket — keeps the /my_dx MQTT slot alive while browsing other pages
  var bgMydxWs = null;
  var bgMydxShouldRun = false;

  function openBgMydxWs(mycall) {
    closeBgMydxWs();
    if (!mycall) return;
    bgMydxShouldRun = true;
    var proto = (location.protocol === 'https:') ? 'wss://' : 'ws://';
    var url = proto + location.host + '/ws?mode=mydx&mycall=' + encodeURIComponent(mycall) + '&txrx=tx';
    function connect() {
      if (!bgMydxShouldRun) return;
      bgMydxWs = new WebSocket(url);
      bgMydxWs.onclose = function () {
        bgMydxWs = null;
        if (bgMydxShouldRun) setTimeout(connect, 5000);
      };
      // Received spots and messages are intentionally ignored
    }
    connect();
  }

  function closeBgMydxWs() {
    bgMydxShouldRun = false;
    if (bgMydxWs) {
      bgMydxWs.onclose = null;
      bgMydxWs.close();
      bgMydxWs = null;
    }
  }

  function sendMydxRelease(mycall) {
    if (!mycall) return;
    fetch('/api/mydx_release', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mycall: mycall}),
      keepalive: true,
    }).catch(function () {});
  }

  function maidenheadToLatLon(grid) {
    if (!grid || grid.length < 4) return null;
    var g = grid.toUpperCase();
    var A = 'A'.charCodeAt(0);
    var lon = (g.charCodeAt(0) - A) * 20 + parseInt(g[2]) * 2 - 180;
    var lat = (g.charCodeAt(1) - A) * 10 + parseInt(g[3]) * 1 - 90;
    if (g.length >= 6) {
      lon += (g.charCodeAt(4) - A) / 12;
      lat += (g.charCodeAt(5) - A) / 24;
      // centre of subsquare
      lon += 1 / 24;
      lat += 1 / 48;
    } else {
      // centre of square
      lon += 1;
      lat += 0.5;
    }
    return [lat, lon];
  }

  function clearStationMarker() {
    stationMarkers.forEach(function (m) { map.removeLayer(m); });
    stationMarkers = [];
  }

  var STATION_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="6" fill="none" stroke="#FFFFFF" stroke-width="4"/><circle cx="12" cy="12" r="10" fill="none" stroke="#FFFFFF" stroke-width="4"/><circle cx="12" cy="12" r="6" fill="none" stroke="#FF6F00" stroke-width="2"/><circle cx="12" cy="12" r="10" fill="none" stroke="#FF6F00" stroke-width="2"/><circle cx="12" cy="12" r="2" fill="#FF6F00"/></svg>';

  function plotStationMarker(grid, callsign) {
    clearStationMarker();
    var ll = maidenheadToLatLon(grid);
    if (!ll) return;
    var icon = L.divIcon({
      html: STATION_SVG,
      className: '',
      iconSize: [24, 24],
      iconAnchor: [12, 12],
      popupAnchor: [0, -14],
    });
    [-360, 0, 360].forEach(function (offset) {
      var m = L.marker([ll[0], ll[1] + offset], { icon: icon }).addTo(map);
      m.bindPopup('<b>' + callsign + '</b><br>' + grid);
      stationMarkers.push(m);
    });
  }

  function init() {
    var initialBands = window.PskUi.fillLegend(function (selected) {
      wsClient.setSelectedBands(selected);
    });
    window.PskActivityDialog.init();

    map = window.PskMap.createMap({
      center: [0, 138],
      zoom: 3,
      minZoom: 2,
      maxZoom: 11,
      maxBounds: GLOBAL_BOUNDS,
      showGrid: true,
      showTerminator: true,
    });

    var statusDotEl = document.getElementById('statusDot');

    function updateDot(text) {
      var t = (text || '').toLowerCase();
      var cls = '';
      if (t.includes('connected') || t.includes('receiving')) cls = 'green';
      else if (t.includes('connecting') || t.includes('loading')) cls = 'yellow';
      else if (t.includes('error') || t.includes('failed') || t.includes('closed') || t.includes('not available')) cls = 'red';
      else if (t.includes('enter') || t.includes('select')) cls = 'cyan';
      statusDotEl.className = cls;
    }

    // Proxy intercepts .textContent writes from ws-client
    // so it doesn't need to know about the dot element.
    statusEl = new Proxy(document.getElementById('statusText'), {
      set: function (target, prop, value) {
        if (prop === 'textContent') {
          var text = String(value).replace(/^status:\s*/, '');
          target.textContent = text;
          updateDot(text);
        } else {
          target[prop] = value;
        }
        return true;
      },
    });

    wsClient = window.PskWsClient.createWsClient({
      map: map,
      statusEl: statusEl,
      colorMap: window.PskUi.COLOR_MAP,
      markerTtl: 180000,
      onUnavailable: function (used, max) {
        mydxSlotInfo = { used: used, max: max };
        var maxStr = max > 0 ? '/' + max : '';
        statusEl.textContent = 'status: proxy not available (' + used + maxStr + ' slots in use)';
      },
      onTimeLimit: function () {
        statusEl.textContent = 'status: time limit reached';
        closeBgMydxWs();
        wsClient.disconnect();
        document.getElementById('timeLimitDialog').showModal();
      },
      onSlots: function (used, max) {
        mydxSlotInfo = { used: used, max: max };
        if (currentPath !== '/my_dx') return;
        // Append slot count to status if currently showing connected
        var statusText = document.getElementById('statusText').textContent || '';
        var maxStr = max > 0 ? '/' + max : '/∞';
        if (statusText.includes('connected')) {
          statusEl.textContent = 'status: connected (' + used + maxStr + ' slots)';
        }
      },
    });

    if (initialBands) wsClient.setSelectedBands(initialBands);

    // Intercept nav link clicks — no page reload
    document.querySelectorAll('.nav-link').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        var path = a.getAttribute('data-path');
        history.pushState(null, '', path);
        navigateTo(path);
      });
    });

    document.getElementById('modeSelect').addEventListener('change', function () {
      var view = VIEWS[currentPath];
      if (!view) return;

      if (view.defaultMode === 'mydx') {
        // modeSelect drives txrx for /my_dx
        currentTxrx = this.value;
        var mycall = (window.PskCookies.getCookie('pskr_mycall') || '').trim().toUpperCase();
        wsClient.clearAll();
        wsClient.resetDataAge();
        wsClient.disconnect();
        if (mycall) {
          wsClient.connect({ currentMode: 'mydx', mycall: mycall, txrx: currentTxrx });
        }
      } else {
        currentMode = this.value;
        wsClient.clearAll();
        wsClient.resetDataAge();
        wsClient.disconnect();
        wsClient.connect({ currentMode: currentMode, local: view.local });
      }
    });

    document.getElementById('dxcallSelect').addEventListener('change', function () {
      currentDxcall = this.value;
      wsClient.clearAll();
      wsClient.disconnect();
      clearStationMarker();
      if (currentDxcall) {
        window.PskCookies.setCookie('pskr_dxcall', currentDxcall, 7);
        wsClient.connect({ currentMode: 'dxpedition', local: false, dxcall: currentDxcall });
        var entry = dxpeditionList.find(function (d) { return d.callsign === currentDxcall; });
        if (entry && entry.grid) {
          plotStationMarker(entry.grid, entry.callsign);
          var ll = maidenheadToLatLon(entry.grid);
          if (ll) map.setView([0, ll[1]], map.getZoom());
        }
        window.PskActivityDialog.open(currentDxcall);
      } else {
        window.PskActivityDialog.close();
        statusEl.textContent = 'status: select a DX-pedition';
      }
    });

    var limitSlider  = document.getElementById('limitSlider');
    var limitValueEl = document.getElementById('limitValue');
    var savedLimit   = parseInt(window.PskCookies.getCookie('pskr_limit') || '1000', 10) || 1000;
    limitSlider.value = savedLimit;
    limitValueEl.textContent = savedLimit;
    wsClient.setMaxMarkers(savedLimit);

    limitSlider.addEventListener('input', function () {
      var n = parseInt(this.value, 10);
      limitValueEl.textContent = n;
      wsClient.setMaxMarkers(n);
      window.PskCookies.setCookie('pskr_limit', n, 365);
    });

    var mycallInput  = document.getElementById('mycallInput');
    var saveBtn      = document.getElementById('saveBtn');
    var cancelBtn    = document.getElementById('cancelBtn');
    var configBtn    = document.getElementById('configBtn');
    var mycallDialog = document.getElementById('mycallDialog');

    function applyMycall(val) {
      var oldMycall = (window.PskCookies.getCookie('pskr_mycall') || '').trim().toUpperCase();
      var mycall = (val || '').trim().toUpperCase();
      if (!mycall) {
        window.PskCookies.setCookie('pskr_mycall', '', 0);
        if (oldMycall) sendMydxRelease(oldMycall);
        closeBgMydxWs();
        wsClient.clearAll();
        wsClient.disconnect();
        statusEl.textContent = 'status: enter your callsign';
        return;
      }
      window.PskCookies.setCookie('pskr_mycall', mycall, 365);
      if (oldMycall && oldMycall !== mycall) sendMydxRelease(oldMycall);
      wsClient.clearAll();
      wsClient.disconnect();
      wsClient.connect({ currentMode: 'mydx', mycall: mycall, txrx: currentTxrx });
    }

    configBtn.addEventListener('click', function () {
      mycallInput.value = (window.PskCookies.getCookie('pskr_mycall') || '').trim().toUpperCase();
      mycallDialog.showModal();
      mycallInput.focus();
      mycallInput.select();
    });

    saveBtn.addEventListener('click', function () {
      applyMycall(mycallInput.value);
      mycallDialog.close();
    });

    cancelBtn.addEventListener('click', function () { mycallDialog.close(); });
    document.getElementById('cancelBtn2').addEventListener('click', function () { mycallDialog.close(); });

    var timeLimitDialog = document.getElementById('timeLimitDialog');
    document.getElementById('timeLimitOkBtn').addEventListener('click', function () { timeLimitDialog.close(); });
    document.getElementById('timeLimitCloseBtn').addEventListener('click', function () { timeLimitDialog.close(); });

    mycallInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter')  { applyMycall(mycallInput.value); mycallDialog.close(); }
      if (e.key === 'Escape') { mycallDialog.close(); }
    });

    map.on('moveend', function () {
      if (!currentPath || currentPath === '/local' || currentPath === '/dxpedition') return;
      var c = map.getCenter();
      var normLng = ((c.lng + 180) % 360 + 360) % 360 - 180;
      window.PskCookies.setCookie('pskr_center_' + currentPath.slice(1), c.lat.toFixed(4) + ',' + normLng.toFixed(4) + ',' + map.getZoom(), 365);
    });

    document.addEventListener('visibilitychange', function () {
      var view = VIEWS[currentPath];
      if (!view || view.type !== 'ws') return;
      if (document.hidden) {
        wsClient.pause();
      } else {
        wsClient.resume();
      }
    });

    window.addEventListener('popstate', function () {
      navigateTo(window.location.pathname);
    });

    navigateTo(window.location.pathname);
  }

  function navigateTo(path) {
    var view = VIEWS[path];
    if (!view) { path = '/dx'; view = VIEWS['/dx']; }

    // If leaving /my_dx, open a background WS to keep the MQTT slot alive
    if (currentPath === '/my_dx') {
      var leavingMycall = (window.PskCookies.getCookie('pskr_mycall') || '').trim().toUpperCase();
      if (leavingMycall && path !== '/my_dx') openBgMydxWs(leavingMycall);
    }

    // Disconnect outgoing connection
    wsClient.disconnect();
    wsClient.clearAll();
    clearStationMarker();
    window.PskActivityDialog.close();

    currentPath = path;
    currentMode = view.defaultMode || 'from_jp';
    document.title = view.title;

    // Highlight active nav link
    document.querySelectorAll('.nav-link').forEach(function (a) {
      a.style.color = a.getAttribute('data-path') === path ? '#0ff' : '#aaa';
    });

    var viewLabelEl   = document.getElementById('viewLabel');
    var modeSelectEl  = document.getElementById('modeSelect');
    var dxcallSelEl   = document.getElementById('dxcallSelect');
    var configBtnEl   = document.getElementById('configBtn');
    var limitCtrlEl   = document.getElementById('limitControl');

    function show(el) { el.style.display = ''; }
    function hide(el) { el.style.display = 'none'; }

    if (view.label) { viewLabelEl.textContent = view.label; show(viewLabelEl); }
    else { hide(viewLabelEl); }

    if (view.showModeSelect) {
      modeSelectEl.innerHTML = '';
      view.modeOptions.forEach(function (o) {
        var opt = document.createElement('option');
        opt.value = o.value;
        opt.textContent = o.label;
        modeSelectEl.appendChild(opt);
      });
      if (view.defaultMode === 'mydx') {
        currentTxrx = view.defaultTxrx || 'tx';
        modeSelectEl.value = currentTxrx;
      } else {
        modeSelectEl.value = currentMode;
      }
      show(modeSelectEl);
    } else {
      hide(modeSelectEl);
    }

    if (view.showDxcallSelect) { show(dxcallSelEl); } else { hide(dxcallSelEl); }
    if (view.showMycall) { show(configBtnEl); } else { hide(configBtnEl); }
    if (view.showLimitSlider) { show(limitCtrlEl); } else { hide(limitCtrlEl); }

    var movieBtn = document.getElementById('movieDownloadBtn');
    if (path === '/dx') {
      movieBtn.textContent = 'Download Yesterday\'s Timelapse';
      movieBtn.onclick = function () {
        var yesterday = new Date(Date.now() - 86400000);
        var yy = yesterday.getUTCFullYear();
        var mm = String(yesterday.getUTCMonth() + 1).padStart(2, '0');
        var dd = String(yesterday.getUTCDate()).padStart(2, '0');
        movieBtn.href = '/timelapse/' + yy + '-' + mm + '-' + dd + '.mp4';
      };
      show(movieBtn);
    } else {
      movieBtn.onclick = null;
      hide(movieBtn);
    }

    map.setMinZoom(view.map.minZoom);
    map.setMaxBounds(view.map.maxBounds);

    var center = view.map.center;
    if (path !== '/local' && path !== '/dxpedition') {
      var saved = window.PskCookies.getCookie('pskr_center_' + path.slice(1));
      if (saved) {
        var parts = saved.split(',');
        var lat = parseFloat(parts[0]), lon = parseFloat(parts[1]);
        if (!isNaN(lat) && !isNaN(lon)) center = [lat, lon];
        var savedZoom = parts[2] ? parseInt(parts[2], 10) : NaN;
        if (!isNaN(savedZoom)) view = Object.assign({}, view, { map: Object.assign({}, view.map, { zoom: savedZoom }) });
      }
    }
    map.setView(center, view.map.zoom);
    wsClient.setMarkerTtl(view.markerTtl);

    // Connect
    if (view.defaultMode === 'mydx') {
      closeBgMydxWs();  // display WS takes over the slot
      var mycall = (window.PskCookies.getCookie('pskr_mycall') || '').trim().toUpperCase();
      if (mycall) {
        wsClient.connect({ currentMode: 'mydx', mycall: mycall, txrx: currentTxrx });
      } else {
        statusEl.textContent = 'status: enter your callsign';
      }
    } else if (view.showDxcallSelect) {
      loadDxpeditions();
    } else {
      wsClient.connect({ currentMode: currentMode, local: view.local || false });
    }
  }

  function loadDxpeditions() {
    var sel = document.getElementById('dxcallSelect');
    while (sel.options.length > 1) sel.remove(1);
    currentDxcall = '';
    statusEl.textContent = 'status: loading DX-peditions...';
    fetch('/api/dxpeditions')
      .then(function (r) { return r.json(); })
      .then(function (list) {
        list.sort(function (a, b) {
          var na = (a.entity_name || '').trim();
          var nb = (b.entity_name || '').trim();
          if (na && !nb) return -1;
          if (!na && nb) return 1;
          return na < nb ? -1 : na > nb ? 1 : 0;
        });
        dxpeditionList = list;
        list.forEach(function (d) {
          var opt = document.createElement('option');
          opt.value = d.callsign;
          opt.textContent = d.entity_name ? d.callsign + ' (' + d.entity_name + ')' : d.callsign;
          sel.appendChild(opt);
        });
        var saved = (window.PskCookies.getCookie('pskr_dxcall') || '').trim().toUpperCase();
        if (saved) {
          var match = list.some(function (d) { return d.callsign === saved; });
          if (match) {
            sel.value = saved;
            sel.dispatchEvent(new Event('change'));
          } else {
            window.PskCookies.setCookie('pskr_dxcall', '', 0);
            statusEl.textContent = 'status: select a DX-pedition';
          }
        } else if (list.length === 1) {
          sel.value = list[0].callsign;
          sel.dispatchEvent(new Event('change'));
        } else {
          statusEl.textContent = 'status: select a DX-pedition';
        }
      })
      .catch(function () {
        statusEl.textContent = 'status: failed to load DX-peditions';
      });
  }

  window.PskRouter = { init: init };
})();
