(function () {
  function initPskReporterPage(config) {
    window.PskUi.fillLegend();

    const map = window.PskMap.createMap(config.map);
    const statusEl = document.getElementById('statusText');
    const modeSelect = document.getElementById('modeSelect');
    const mycallInput = document.getElementById('mycallInput');
    const saveBtn = document.getElementById('saveBtn');

    const state = {
      currentMode: config.mode || (modeSelect ? modeSelect.value : 'from_jp'),
      local: !!config.local,
      requireMycall: !!config.cookieKey,
      mycall: '',
    };

    if (config.cookieKey) {
      state.mycall = (window.PskCookies.getCookie(config.cookieKey) || '').trim().toUpperCase();
      if (mycallInput) {
        mycallInput.value = state.mycall;
      }
    }

    const wsClient = window.PskWsClient.createWsClient({
      map,
      statusEl,
      colorMap: window.PskUi.COLOR_MAP,
    });

    if (config.showStatus) {
      wsClient.startStatusTimer(function () {
        return state.currentMode;
      });
    }

    function reconnect() {
      wsClient.clearAll();
      wsClient.disconnect();
      wsClient.connect(state);
    }

    if (modeSelect) {
      modeSelect.value = state.currentMode;
      modeSelect.addEventListener('change', function () {
        state.currentMode = modeSelect.value;
        wsClient.resetDataAge();
        reconnect();
      });
    }

    if (saveBtn && mycallInput && config.cookieKey) {
      function applyMyCall(newCall) {
        state.mycall = (newCall || '').trim().toUpperCase();
        mycallInput.value = state.mycall;

        if (!state.mycall) {
          window.PskCookies.setCookie(config.cookieKey, '', 0);
          wsClient.clearAll();
          wsClient.disconnect();
          if (statusEl) {
            statusEl.textContent = 'status: enter your callsign';
          }
          return;
        }

        window.PskCookies.setCookie(config.cookieKey, state.mycall, 365);
        reconnect();
      }

      saveBtn.addEventListener('click', function () {
        applyMyCall(mycallInput.value);
      });

      mycallInput.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
          applyMyCall(mycallInput.value);
        }
      });
    }

    if (config.cookieKey && !state.mycall) {
      if (statusEl) {
        statusEl.textContent = 'status: enter your callsign';
      }
      if (mycallInput) {
        mycallInput.focus();
      }
    } else if (!document.hidden) {
      wsClient.connect(state);
    }

    document.addEventListener('visibilitychange', function () {
      if (document.hidden) {
        wsClient.disconnect();
      } else {
        reconnect();
      }
    });
  }

  window.initPskReporterPage = initPskReporterPage;
})();
