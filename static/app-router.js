(function () {
  'use strict';

  var GLOBAL_BOUNDS = [[-90, -200], [90, 200]];
  var JAPAN_BOUNDS  = [[20.0, 122.0], [46.5, 154.0]];

  var VIEWS = {
    '/dx': {
      title: 'DX Watch',
      type: 'ws',
      defaultMode: 'from_jp',
      local: false,
      markerTtl: 180000,
      showModeSelect: true,
      modeOptions: [
        { value: 'from_jp', label: 'JP→World' },
        { value: 'to_jp',   label: 'World→JP' },
      ],
      map: { center: [0, 0], zoom: 3, minZoom: 3, maxBounds: GLOBAL_BOUNDS },
    },
    '/local': {
      title: 'DX Watch: Local',
      type: 'ws',
      defaultMode: 'from_jp',
      local: true,
      markerTtl: 180000,
      label: 'JP↔JP',
      showModeSelect: true,
      modeOptions: [
        { value: 'from_jp', label: 'marker=RL' },
        { value: 'to_jp',   label: 'marker=SL' },
      ],
      map: { center: [36.2, 138.2], zoom: 5, minZoom: 5, maxBounds: JAPAN_BOUNDS },
    },
    '/my_dx': {
      title: 'DX Watch: MyDX',
      type: 'mqtt',
      markerTtl: 180000,
      showMycall: true,
      map: { center: [20, 0], zoom: 3, minZoom: 3, maxBounds: GLOBAL_BOUNDS },
    },
    '/dxpedition': {
      title: 'DX Watch: DX-pedition',
      type: 'ws',
      defaultMode: 'dxpedition',
      local: false,
      markerTtl: 900000,
      showDxcallSelect: true,
      map: { center: [0, 0], zoom: 3, minZoom: 3, maxBounds: GLOBAL_BOUNDS },
    },
    '/jq3ikn': {
      title: 'DX Watch: JQ3IKN',
      type: 'ws',
      defaultMode: 'jq3ikn',
      local: false,
      markerTtl: 900000,
      label: 'JQ3IKN',
      map: { center: [0, 0], zoom: 3, minZoom: 3, maxBounds: GLOBAL_BOUNDS },
    },
  };

  var map, wsClient, mqttClient, statusEl;
  var currentPath = null;
  var currentMode = 'from_jp';
  var currentDxcall = '';

  function init() {
    window.PskUi.fillLegend();

    map = window.PskMap.createMap({
      center: [0, 0],
      zoom: 3,
      minZoom: 3,
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
      else if (t.includes('error') || t.includes('failed') || t.includes('closed')) cls = 'red';
      else if (t.includes('enter') || t.includes('select')) cls = 'cyan';
      statusDotEl.className = cls;
    }

    // Proxy intercepts .textContent writes from ws-client and mqtt-client
    // so neither needs to know about the dot element.
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
    });

    mqttClient = window.PskMqttClient.createMqttClient({
      map: map,
      statusEl: statusEl,
      colorMap: window.PskUi.COLOR_MAP,
      markerTtl: 180000,
    });
    mqttClient.startStatusTimer();

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
      currentMode = this.value;
      var view = VIEWS[currentPath];
      if (!view) return;
      wsClient.clearAll();
      wsClient.disconnect();
      wsClient.connect({ currentMode: currentMode, local: view.local });
    });

    document.getElementById('dxcallSelect').addEventListener('change', function () {
      currentDxcall = this.value;
      wsClient.clearAll();
      wsClient.disconnect();
      if (currentDxcall) {
        wsClient.connect({ currentMode: 'dxpedition', local: false, dxcall: currentDxcall });
      } else {
        statusEl.textContent = 'status: select a DX-pedition';
      }
    });

    var mycallInput = document.getElementById('mycallInput');
    var saveBtn = document.getElementById('saveBtn');

    function applyMycall(val) {
      var mycall = (val || '').trim().toUpperCase();
      mycallInput.value = mycall;
      if (!mycall) {
        window.PskCookies.setCookie('pskr_mycall', '', 0);
        mqttClient.disconnect();
        mqttClient.clearAll();
        statusEl.textContent = 'status: enter your callsign';
        return;
      }
      window.PskCookies.setCookie('pskr_mycall', mycall, 365);
      mqttClient.connect(mycall);
    }

    saveBtn.addEventListener('click', function () { applyMycall(mycallInput.value); });
    mycallInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') applyMycall(mycallInput.value);
    });

    document.addEventListener('visibilitychange', function () {
      var view = VIEWS[currentPath];
      if (!view) return;
      if (document.hidden) {
        if (view.type === 'ws') wsClient.disconnect();
        else mqttClient.disconnect();
      } else {
        reconnectCurrent();
      }
    });

    window.addEventListener('popstate', function () {
      navigateTo(window.location.pathname);
    });

    navigateTo(window.location.pathname);
  }

  function reconnectCurrent() {
    var view = VIEWS[currentPath];
    if (!view) return;
    if (view.type === 'mqtt') {
      var mycall = (window.PskCookies.getCookie('pskr_mycall') || '').trim().toUpperCase();
      if (mycall) mqttClient.connect(mycall);
    } else if (view.defaultMode === 'dxpedition') {
      if (currentDxcall) {
        wsClient.connect({ currentMode: 'dxpedition', local: false, dxcall: currentDxcall });
      }
    } else {
      wsClient.connect({ currentMode: currentMode, local: view.local });
    }
  }

  function navigateTo(path) {
    var view = VIEWS[path];
    if (!view) { path = '/dx'; view = VIEWS['/dx']; }

    // Disconnect outgoing connections
    wsClient.disconnect();
    wsClient.clearAll();
    if (currentPath === '/my_dx') {
      mqttClient.disconnect();
      mqttClient.clearAll();
    }

    currentPath = path;
    currentMode = view.defaultMode || 'from_jp';
    document.title = view.title;

    // Highlight active nav link
    document.querySelectorAll('.nav-link').forEach(function (a) {
      a.style.color = a.getAttribute('data-path') === path ? '#0ff' : '#aaa';
    });

    // Update UI visibility
    var viewLabelEl   = document.getElementById('viewLabel');
    var modeSelectEl  = document.getElementById('modeSelect');
    var dxcallSelEl   = document.getElementById('dxcallSelect');
    var mycallLabelEl = document.getElementById('mycallLabel');
    var mycallInput   = document.getElementById('mycallInput');
    var saveBtn       = document.getElementById('saveBtn');

    function show(el) { el.style.display = ''; }
    function hide(el) { el.style.display = 'none'; }

    // Static label (JP↔JP or JQ3IKN)
    if (view.label) { viewLabelEl.textContent = view.label; show(viewLabelEl); }
    else { hide(viewLabelEl); }

    // Mode select
    if (view.showModeSelect) {
      var opts = modeSelectEl.querySelectorAll('option');
      // Rebuild options to match this view
      modeSelectEl.innerHTML = '';
      view.modeOptions.forEach(function (o) {
        var opt = document.createElement('option');
        opt.value = o.value;
        opt.textContent = o.label;
        modeSelectEl.appendChild(opt);
      });
      modeSelectEl.value = currentMode;
      show(modeSelectEl);
    } else {
      hide(modeSelectEl);
    }

    // DX-pedition select
    if (view.showDxcallSelect) { show(dxcallSelEl); } else { hide(dxcallSelEl); }

    // Mycall UI
    if (view.showMycall) { show(mycallLabelEl); show(mycallInput); show(saveBtn); }
    else { hide(mycallLabelEl); hide(mycallInput); hide(saveBtn); }

    // Apply map settings for this view
    map.setMinZoom(view.map.minZoom);
    map.setMaxBounds(view.map.maxBounds);
    map.setView(view.map.center, view.map.zoom);

    // Apply marker TTL
    wsClient.setMarkerTtl(view.markerTtl);

    // Connect
    if (view.type === 'mqtt') {
      var mycall = (window.PskCookies.getCookie('pskr_mycall') || '').trim().toUpperCase();
      mycallInput.value = mycall;
      if (mycall) {
        mqttClient.connect(mycall);
      } else {
        document.getElementById('statusText').textContent = 'status: enter your callsign';
        mycallInput.focus();
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
        list.forEach(function (d) {
          var opt = document.createElement('option');
          opt.value = d.callsign;
          opt.textContent = d.entity_name ? d.callsign + ' (' + d.entity_name + ')' : d.callsign;
          sel.appendChild(opt);
        });
        if (list.length === 1) {
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
