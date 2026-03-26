(function () {
  // Bands shown individually in the dialog; everything else → Other
  var MAIN_BANDS = [80, 40, 30, 20, 17, 15, 12, 10];
  var OTHER_ID   = -1;

  var STORAGE_KEY = 'pskr_activity_bands';

  var dialog, titleBar, titleText, heatmapEl, bandsEl;
  var currentCallsign = '';
  var activityData = [];
  var selectedBands = null; // null = all bands

  function saveBands() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(selectedBands));
    } catch (e) {}
  }

  function loadBands() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw === null) return;
      selectedBands = JSON.parse(raw); // null or array
    } catch (e) {}
  }

  // ── Color scale ──────────────────────────────────────────────────
  function cellColor(count, maxCount) {
    if (count === 0 || maxCount === 0) return '#262636';
    var t = Math.log(count + 1) / Math.log(maxCount + 1);
    var lightness = Math.round(15 + t * 60);
    return 'hsl(35,90%,' + lightness + '%)';
  }

  // ── Date helpers ─────────────────────────────────────────────────
  function getLast7Days() {
    var days = [];
    for (var i = 6; i >= 0; i--) {
      var d = new Date(Date.now() - i * 86400000);
      days.push(d.toISOString().slice(0, 10));
    }
    return days;
  }

  // ── Grid building ─────────────────────────────────────────────────
  function buildGrid(data, bands) {
    var days = getLast7Days();
    var grid = {};
    days.forEach(function (d) { grid[d] = new Array(24).fill(0); });
    data.forEach(function (row) {
      if (bands !== null) {
        var isMain  = MAIN_BANDS.indexOf(row.band) !== -1;
        var wantIt  = isMain  && bands.indexOf(row.band) !== -1;
        var wantOther = !isMain && bands.indexOf(OTHER_ID)  !== -1;
        if (!wantIt && !wantOther) return;
      }
      var day = row.hour_utc.slice(0, 10);
      var hour = parseInt(row.hour_utc.slice(11, 13), 10);
      if (grid[day] !== undefined) grid[day][hour] += row.spot_count;
    });
    return { days: days, grid: grid };
  }

  // ── Heatmap render ────────────────────────────────────────────────
  function renderHeatmap() {
    var result = buildGrid(activityData, selectedBands);
    var days = result.days;
    var grid = result.grid;

    var maxCount = 0;
    days.forEach(function (d) {
      grid[d].forEach(function (c) { if (c > maxCount) maxCount = c; });
    });

    var nowHour = new Date().getUTCHours();

    var html = '<table class="act-table"><thead><tr><th></th>';
    for (var h = 0; h < 24; h++) {
      var label = h < 10 ? '0' + h : '' + h;
      if (h === nowHour) {
        html += '<th style="color:#f90;font-weight:bold">' + label + '</th>';
      } else {
        html += '<th>' + label + '</th>';
      }
    }
    html += '</tr></thead><tbody>';

    days.forEach(function (day) {
      html += '<tr><td class="act-day">' + day.slice(5) + '</td>';
      for (var h = 0; h < 24; h++) {
        var count = grid[day][h];
        var bg = cellColor(count, maxCount);
        var tip = count > 0 ? count + ' spot' + (count > 1 ? 's' : '') : '';
        html += '<td class="act-cell" style="background:' + bg + '" title="' + tip + '"></td>';
      }
      html += '</tr>';
    });

    html += '</tbody></table>';
    heatmapEl.innerHTML = html;
  }

  // ── Band checkboxes ───────────────────────────────────────────────
  function renderBands() {
    var ui = window.PskUi || {};
    var colorMap = ui.COLOR_MAP || {};
    var legendSvg = ui.bandLegendSvg || function (b, c) {
      return '<span style="display:inline-block;width:20px;height:20px;background:' + c + '"></span>';
    };
    var entries = MAIN_BANDS.map(function (b) { return { id: b, label: b + 'm', svgBand: b }; });
    entries.push({ id: OTHER_ID, label: 'Other', svgBand: 0 });
    var allCount = entries.length;

    bandsEl.innerHTML = '';
    entries.forEach(function (e) {
      var isOn = !selectedBands || selectedBands.indexOf(e.id) !== -1;
      var item = document.createElement('div');
      item.className = 'act-band-label' + (isOn ? '' : ' off');
      item.dataset.band = String(e.id);

      var dot = document.createElement('span');
      dot.className = 'act-band-dot';
      dot.innerHTML = legendSvg(e.svgBand, colorMap[e.svgBand] || '#888');

      var lbl = document.createElement('span');
      lbl.textContent = e.label;

      item.appendChild(dot);
      item.appendChild(lbl);
      bandsEl.appendChild(item);

      item.addEventListener('click', function () {
        item.classList.toggle('off');
        var onItems = Array.prototype.filter.call(
          bandsEl.querySelectorAll('.act-band-label'),
          function (el) { return !el.classList.contains('off'); }
        );
        selectedBands = onItems.length === allCount
          ? null
          : onItems.map(function (el) { return parseInt(el.dataset.band, 10); });
        saveBands();
        renderHeatmap();
      });
    });
  }

  // ── Fetch & render ────────────────────────────────────────────────
  function fetchAndRender() {
    if (!currentCallsign) return;
    heatmapEl.innerHTML = '<div class="act-loading">Loading…</div>';
    var callsigns = currentCallsign.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    fetch('/api/dxpedition_activity?callsign=' + encodeURIComponent(callsigns.join(',')))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        activityData = data;
        renderHeatmap();
      })
      .catch(function () {
        heatmapEl.innerHTML = '<div class="act-loading">Failed to load activity.</div>';
      });
  }

  // ── Drag ──────────────────────────────────────────────────────────
  function initDrag() {
    var dragging = false;
    var ox = 0, oy = 0;

    titleBar.addEventListener('mousedown', function (e) {
      if (e.target.tagName === 'BUTTON') return;
      dragging = true;
      ox = e.clientX - dialog.offsetLeft;
      oy = e.clientY - dialog.offsetTop;
      e.preventDefault();
    });

    document.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      dialog.style.right = 'auto';
      dialog.style.left = (e.clientX - ox) + 'px';
      dialog.style.top  = (e.clientY - oy) + 'px';
    });

    document.addEventListener('mouseup', function () { dragging = false; });
  }

  // ── Public API ────────────────────────────────────────────────────
  function init() {
    dialog    = document.getElementById('activityDialog');
    titleBar  = document.getElementById('activityDialogTitleBar');
    titleText = document.getElementById('activityDialogTitleText');
    heatmapEl = document.getElementById('activityDialogHeatmap');
    bandsEl   = document.getElementById('activityDialogBands');

    document.getElementById('activityDialogClose')
      .addEventListener('click', close);
    document.getElementById('activityDialogRefresh')
      .addEventListener('click', fetchAndRender);

    initDrag();
  }

  function open(callsign) {
    currentCallsign = callsign;
    loadBands();

    var labels = callsign.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    titleText.textContent = labels.join(' / ') + ' — 7-day Activity (UTC)';

    dialog.style.display = 'flex';
    renderBands();
    fetchAndRender();
  }

  function close() {
    if (dialog) dialog.style.display = 'none';
    currentCallsign = '';
    activityData = [];
  }

  window.PskActivityDialog = { init: init, open: open, close: close };
})();
